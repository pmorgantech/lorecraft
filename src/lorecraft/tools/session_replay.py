"""Session record & playback — scenario format + `record` (Sprint 43, Phase 1).

Records a real player session out of the audit log as a *scenario* JSON file,
and provides the shared audit-trail normaliser the replay side diffs goldens
with. The playback engine itself lives with the simulation harness
(`tests/simulation/replay.py`) because it drives `VirtualPlayer`s against a
live server; this module stays importable from production code paths (it only
reads an audit DB).

Scenario format (`docs/session_replay.md`):

    {
      "version": 1,
      "description": "petem clears the Wandering Crow quest",
      "world_yaml": "world_content/world.yaml",
      "rng_seed": 1,
      "actors": ["player-1"],
      "commands": [
        {"t": 0.0, "actor": "player-1", "raw": "look"},
        {"t": 1.4, "actor": "player-1", "raw": "go east"}
      ]
    }

Actors are *logical* ids — replay maps each onto a freshly created player, so
a one-player recording can later be fanned out to N players (Phase 2).

CLI:

    python -m lorecraft.tools.session_replay record \\
        --audit-db audit.db --actor player-1 -o scenario.json \\
        [--since <unix-ts>] [--description ...] [--world-yaml ...] [--rng-seed N]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlmodel import Session, col, create_engine, select

from lorecraft.engine.models.audit import AuditEvent

SCENARIO_VERSION = 1

DEFAULT_WORLD_YAML = "world_content/world.yaml"

# The audit event types that carry a player-issued command (payload `raw`).
COMMAND_EVENT_TYPES = ("command_executed", "command_blocked", "command_failed")

# One audit event, reduced to the fields that must be stable across replays.
# Run-specific values (transaction/correlation ids, timestamps, generated
# player UUIDs) are deliberately excluded — same shape the audit-regression
# test has always compared on.
NormalizedEvent = dict[str, str | None]


@dataclass
class ScenarioCommand:
    """One recorded command: `t` seconds from scenario start, by `actor`."""

    t: float
    actor: str
    raw: str


@dataclass
class Scenario:
    description: str = ""
    world_yaml: str = DEFAULT_WORLD_YAML
    rng_seed: int | None = None
    actors: list[str] = field(default_factory=list)
    commands: list[ScenarioCommand] = field(default_factory=list)
    version: int = SCENARIO_VERSION

    def commands_for(self, actor: str) -> list[ScenarioCommand]:
        return [command for command in self.commands if command.actor == actor]


def save_scenario(scenario: Scenario, path: Path) -> None:
    document = {
        "version": scenario.version,
        "description": scenario.description,
        "world_yaml": scenario.world_yaml,
        "rng_seed": scenario.rng_seed,
        "actors": scenario.actors,
        "commands": [asdict(command) for command in scenario.commands],
    }
    path.write_text(json.dumps(document, indent=2) + "\n")


def load_scenario(path: Path) -> Scenario:
    document = json.loads(path.read_text())
    version = document.get("version")
    if version != SCENARIO_VERSION:
        raise ValueError(
            f"unsupported scenario version {version!r} in {path} "
            f"(this build reads version {SCENARIO_VERSION})"
        )
    return Scenario(
        description=document.get("description", ""),
        world_yaml=document.get("world_yaml", DEFAULT_WORLD_YAML),
        rng_seed=document.get("rng_seed"),
        actors=list(document.get("actors", [])),
        commands=[
            ScenarioCommand(t=float(entry["t"]), actor=entry["actor"], raw=entry["raw"])
            for entry in document.get("commands", [])
        ],
    )


def record_scenario(
    audit_db_path: Path,
    actor_id: str,
    *,
    since: float | None = None,
    description: str = "",
    world_yaml: str = DEFAULT_WORLD_YAML,
    rng_seed: int | None = None,
) -> Scenario:
    """Project one actor's command stream out of an audit DB.

    Every `command_executed`/`_blocked`/`_failed` event carries the raw
    command line in its payload; `t` is the delta from the first matched
    event's `real_time`. The recorded actor id becomes the scenario's single
    logical actor. World YAML and RNG seed aren't recorded in the audit DB,
    so the caller supplies them (they stamp the scenario for replay).
    """
    engine = create_engine(f"sqlite:///{audit_db_path}")
    with Session(engine) as session:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.actor_id == actor_id)
            .where(col(AuditEvent.event_type).in_(COMMAND_EVENT_TYPES))
            .order_by(col(AuditEvent.real_time), col(AuditEvent.id))
        )
        if since is not None:
            statement = statement.where(AuditEvent.real_time >= since)
        events = list(session.exec(statement).all())

    commands: list[ScenarioCommand] = []
    start: float | None = None
    for event in events:
        raw = event.payload_json.get("raw")
        if not isinstance(raw, str) or not raw:
            continue
        if start is None:
            start = event.real_time
        commands.append(
            ScenarioCommand(
                t=round(event.real_time - start, 3), actor=actor_id, raw=raw
            )
        )
    if not commands:
        raise ValueError(f"no command events for actor {actor_id!r} in {audit_db_path}")
    return Scenario(
        description=description,
        world_yaml=world_yaml,
        rng_seed=rng_seed,
        actors=[actor_id],
        commands=commands,
    )


def normalize_events(events: Iterable[AuditEvent]) -> list[NormalizedEvent]:
    """Reduce an audit trail to its replay-stable shape (for golden diffs)."""
    return [
        {
            "event_type": event.event_type,
            "summary": event.summary,
            "target_id": event.target_id,
            "room_id": event.room_id,
            "severity": event.severity,
        }
        for event in events
    ]


def percentile(sorted_ms: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile; `sorted_ms` must be sorted ascending."""
    if not sorted_ms:
        return 0.0
    index = min(len(sorted_ms) - 1, int(len(sorted_ms) * fraction))
    return round(sorted_ms[index], 3)


def latency_report(
    latencies_ms: Iterable[float],
    *,
    players: int,
    commands_per_player: int,
    jitter_ms: int = 0,
) -> dict[str, float | int]:
    """The Sprint 37.3 load-test report shape (p50/p95/p99/max), shared so
    fan-out replay and the load test emit byte-compatible JSON for scripted
    before/after diffs."""
    ordered = sorted(latencies_ms)
    return {
        "players": players,
        "commands_per_player": commands_per_player,
        "total_commands": len(ordered),
        "jitter_ms": jitter_ms,
        "p50_ms": percentile(ordered, 0.50),
        "p95_ms": percentile(ordered, 0.95),
        "p99_ms": percentile(ordered, 0.99),
        "max_ms": round(ordered[-1], 3) if ordered else 0.0,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m lorecraft.tools.session_replay",
        description="Record player sessions from the audit log as scenario JSON.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser(
        "record", help="project one actor's commands from an audit DB"
    )
    record.add_argument("--audit-db", type=Path, required=True)
    record.add_argument("--actor", required=True, help="actor/player id to record")
    record.add_argument("-o", "--output", type=Path, required=True)
    record.add_argument(
        "--since", type=float, default=None, help="only events at/after this unix time"
    )
    record.add_argument("--description", default="")
    record.add_argument("--world-yaml", default=DEFAULT_WORLD_YAML)
    record.add_argument(
        "--rng-seed",
        type=int,
        default=None,
        help="seed to stamp for deterministic replay (not recoverable from the audit DB)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "record":
        if not args.audit_db.exists():
            print(f"audit DB not found: {args.audit_db}", file=sys.stderr)
            return 1
        try:
            scenario = record_scenario(
                args.audit_db,
                args.actor,
                since=args.since,
                description=args.description,
                world_yaml=args.world_yaml,
                rng_seed=args.rng_seed,
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        save_scenario(scenario, args.output)
        print(
            f"recorded {len(scenario.commands)} commands for {args.actor} "
            f"-> {args.output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
