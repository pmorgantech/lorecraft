"""Performance baseline micro-benchmark (roadmap perf band, Sprint 36.1).

Drives the *real* command hot paths — parse, condition evaluation, full
command dispatch, and a game-DB commit — against the real Ashmoore world
loaded into a disposable SQLite DB, and reports p50/p95/p99 latency per
operation.

This is the **"before" picture**: run it and record the numbers *before*
implementing any caching/batching, then re-run after to prove the effect. It
deliberately does not touch threads, servers, or sockets — the scheduler-tick
and broadcast-fan-out paths are server-loop concerns measured by a load test,
not here.

Usage:
    .venv/bin/python scripts/perf_baseline.py [--iterations N] [--json]

Caveats (documented, not bugs):
- `audit=None`, so audit-log writes are not exercised (the real `/command`
  path writes an audit event per command to a *separate* engine). The commit
  measured here is the game-state commit only.
- File-backed SQLite (not `:memory:`) so `db_commit` includes realistic fsync
  cost, matching production.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.config import Settings
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.meters import MeterDef, get_registry as get_meter_registry
from lorecraft.engine.game.parser import parse_command
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Item, Room, WorldClock
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.services.mobile_route import (
    MobileRouteService,
    RouteHooks,
    RouteSpec,
    Waypoint,
)
from lorecraft.engine.services.scheduler import SchedulerService
from lorecraft.features.item_components.components import (
    register as register_item_components,
)
from lorecraft.world.bootstrap import ensure_world_bootstrapped

# Register standard item components so item paths behave like the real app.
register_item_components()

# Read-only commands: repeatable (no player-state mutation), so timing them in a
# tight loop is meaningful and stable.
READONLY_COMMANDS = ["look", "inventory", "who"]


def _percentiles(samples_ms: list[float]) -> dict[str, float]:
    ordered = sorted(samples_ms)
    n = len(ordered)

    def pct(p: float) -> float:
        if n == 1:
            return ordered[0]
        idx = min(n - 1, int(round((p / 100.0) * (n - 1))))
        return ordered[idx]

    return {
        "n": n,
        "mean": statistics.fmean(ordered),
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "max": ordered[-1],
    }


def _fmt(name: str, stats: dict[str, float]) -> str:
    return (
        f"{name:<24} n={int(stats['n']):>5}  "
        f"mean={stats['mean']:7.3f}  p50={stats['p50']:7.3f}  "
        f"p95={stats['p95']:7.3f}  p99={stats['p99']:7.3f}  "
        f"max={stats['max']:7.3f}   (ms)"
    )


def build_harness(
    db_path: Path,
) -> tuple[CommandEngine, GameContext, Session, CommandRegistry]:
    """Bootstrap the real world into a disposable DB and wire a GameContext."""
    game_engine = create_engine(f"sqlite:///{db_path}")
    audit_engine = create_engine("sqlite://")
    create_tables(game_engine=game_engine, audit_engine=audit_engine)

    repo_root = Path(__file__).resolve().parents[1]
    settings = Settings(
        database_path=str(db_path),
        world_yaml_path=str(repo_root / "world_content" / "world.yaml"),
    )
    ensure_world_bootstrapped(game_engine, settings)

    # The proof-of-primitive "hp" meter def the real app registers at lifespan.
    meter_registry = get_meter_registry()
    if "hp" not in meter_registry:
        meter_registry.register(
            MeterDef(key="hp", base_maximum=lambda _et, _eid, _s: 100.0)
        )

    session = Session(game_engine)
    player = session.get(Player, settings.seed_player_id)
    assert player is not None, "seed player missing after bootstrap"
    room = session.get(Room, player.current_room_id)
    assert room is not None, "seed player's room missing"

    rng = GameRng(seed=1)
    ctx = GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=rng,
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="perf"
        ),
        session_id="perf",
        commit_state=session.commit,
    )

    registry = CommandRegistry()
    register_all_commands(registry)
    return CommandEngine(registry, RuleEngine()), ctx, session, registry


def _measure_scheduler_tick(
    db_dir: Path, job_counts: tuple[int, ...], iterations: int
) -> dict[str, dict[str, float]]:
    """Cost of one scheduler tick that dispatches N due `mobile_route` jobs.

    Each due job is handled by `MobileRouteService` with its own `Session` +
    commit (the current design). This quantifies the per-tick cost Sprint 37.1
    batching would target. File-backed SQLite, so commit fsync is realistic.

    All N routes share dwell/travel, so they stay in lockstep and every integer
    tick dispatches exactly N due jobs (depart/arrive alternating). Dispatched
    ScheduledJob rows accumulate across ticks — kept to a modest `iterations` so
    the `due()` scan growth doesn't dominate the signal we care about (how tick
    cost scales with job count).
    """
    results: dict[str, dict[str, float]] = {}
    waypoints = (
        Waypoint(position_id="a", x=0, y=0, dwell_ticks=1.0, travel_ticks=1.0),
        Waypoint(position_id="b", x=1, y=0, dwell_ticks=1.0, travel_ticks=1.0),
    )
    for n in job_counts:
        engine = create_engine(f"sqlite:///{db_dir / f'sched-{n}.db'}")
        create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
        with Session(engine) as setup_session:
            setup_session.add(WorldClock(game_epoch=0.0, real_epoch=0.0))
            setup_session.commit()

        bus = EventBus()
        scheduler = SchedulerService(engine, GameRng())
        scheduler.register(bus)
        service = MobileRouteService(engine, scheduler)
        service.register(bus)
        for i in range(n):
            service.add_route(
                RouteSpec(route_id=f"route_{i}", waypoints=waypoints), RouteHooks()
            )
            service.start(f"route_{i}")  # schedules a depart-check job at epoch 1

        epoch = 1.0
        for _ in range(3):  # warm up: compile queries, fill caches
            bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": epoch}), None)
            epoch += 1.0
        samples: list[float] = []
        for _ in range(iterations):
            start = time.perf_counter()
            bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": epoch}), None)
            samples.append((time.perf_counter() - start) * 1000)
            epoch += 1.0
        results[f"scheduler_tick@{n}jobs"] = _percentiles(samples)
    return results


def _load_inventory(ctx: GameContext, session: Session, count: int) -> None:
    """Spawn `count` distinct fungible items into the player's inventory so the
    parser's visible-entity/inventory resolution has a realistic load to scan."""
    pid = ctx.player.id
    for i in range(count):
        item_id = f"widget_{i}"
        if session.get(Item, item_id) is None:
            session.add(
                Item(id=item_id, name=f"widget {i}", description="a test widget")
            )
    session.commit()
    for i in range(count):
        ctx.item_location.spawn(f"widget_{i}", Location("player", pid))
    session.commit()


def run(iterations: int, as_json: bool) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "perf-game.db"
        engine, ctx, session, registry = build_harness(db_path)

        look_cmd = registry.get("look")

        # Warm up (import caches, SQLAlchemy compilation, first-touch paths).
        for _ in range(20):
            parse_command("look", context=ctx)
            engine.handle_command("look", ctx)
            ctx.messages.clear()

        results: dict[str, dict[str, float]] = {}

        # 1) parse_command in isolation (no dispatch).
        for label, raw in (
            ("parse:look", "look"),
            ("parse:examine", "examine lantern"),
        ):
            samples: list[float] = []
            for _ in range(iterations):
                t = time.perf_counter()
                parse_command(raw, context=ctx)
                samples.append((time.perf_counter() - t) * 1000)
            results[label] = _percentiles(samples)

        # 2) condition evaluation in isolation (registry gate for one command).
        if look_cmd is not None:
            samples = []
            for _ in range(iterations):
                t = time.perf_counter()
                registry.evaluate_conditions(look_cmd, ctx)
                samples.append((time.perf_counter() - t) * 1000)
            results["condition_eval:look"] = _percentiles(samples)

        # 3) full handle_command for each read-only verb (repeatable).
        for verb in READONLY_COMMANDS:
            samples = []
            for _ in range(iterations):
                t = time.perf_counter()
                engine.handle_command(verb, ctx)
                samples.append((time.perf_counter() - t) * 1000)
                ctx.messages.clear()
                ctx.updates.clear()
            results[f"handle:{verb}"] = _percentiles(samples)

        # 4) bare game-DB commit cost (no-op transaction → fsync overhead).
        samples = []
        for _ in range(iterations):
            t = time.perf_counter()
            session.commit()
            samples.append((time.perf_counter() - t) * 1000)
        results["db_commit:noop"] = _percentiles(samples)

        # 5) parse scaling: how does parse cost grow with visible-entity count?
        #    This is the decision input for parser caching — a cache only pays
        #    off if parse is expensive, and parse resolution is O(entities).
        for extra in (25, 100):
            _load_inventory(ctx, session, extra)
            samples = []
            for _ in range(iterations):
                t = time.perf_counter()
                parse_command("examine widget", context=ctx)
                samples.append((time.perf_counter() - t) * 1000)
            results[f"parse:examine@{extra}items"] = _percentiles(samples)

        # 6) scheduler tick dispatching N due mobile_route jobs — the per-tick,
        #    per-job-commit cost Sprint 37.1 batching would target. Much heavier
        #    than the micro-ops above (real per-job commits), so a small fixed
        #    sample count rather than `iterations`.
        results.update(
            _measure_scheduler_tick(Path(tmp), job_counts=(1, 10, 50), iterations=10)
        )

        session.close()

    if as_json:
        print(json.dumps(results, indent=2))
        return

    print(f"\nPerformance baseline — {iterations} iterations/op, real Ashmoore world")
    print("=" * 92)
    for name, stats in results.items():
        print(_fmt(name, stats))
    print("=" * 92)
    print(
        "Notes: audit writes not exercised (audit=None); db_commit is game-state only, "
        "file-backed SQLite.\nscheduler_tick@Njobs measures the current per-job-commit "
        "cost (Sprint 37.1 batching target); broadcast_send is a server-loop path — "
        "measured by the multi-player load test (tests/simulation/test_load.py)."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iterations", type=int, default=2000)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()
    run(args.iterations, args.json)


if __name__ == "__main__":
    main()
