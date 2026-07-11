"""Phase A acceptance harness — all scripting-engine primitives working in concert.

This is the "how do I know Phase A is done" test (`docs/scripting_engine_design.md` §6, A.5). It
builds a small demo world and wires every Phase-A service onto one bus + clock, then advances
time on a fixed RNG seed and asserts the observable outcomes:

* A3 — a patrolling guard walks its route (emits NPC_MOVED).
* A2 — when the guard reaches the player's room, its `encounter` trigger fires (from the NPC
  side), setting a flag on the player.
* A5 — a storm front applies a room effect across a zone.
* A6 — a spawner tops the zone's population up to its target.

Plus a determinism check: two identical seeded runs produce identical observable state — the
replay-faithfulness invariant (§7) that every autonomous roll goes through `GameRng`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.engine.game import effects as effects_module
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.effects import EffectDef
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import NPC, Exit, Room, WorldClock
from lorecraft.engine.scripting.triggers import Trigger, TriggerService
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.npc.dialogue_conditions import get_registry as dialogue_registry
from lorecraft.features.npc.side_effects import get_registry as effect_registry
from lorecraft.features.npc_ai.service import NpcBehaviorService
from lorecraft.features.spawns.service import SpawnControllerService
from lorecraft.features.weather.fronts import WeatherFrontService

AREA = "town"
ROOMS = ["plaza", "market", "gate"]  # guard patrols plaza -> market -> gate


def _seed(engine: Engine) -> None:
    with Session(engine) as session:
        for i, rid in enumerate(ROOMS):
            session.add(
                Room(
                    id=rid,
                    name=rid.title(),
                    description="d",
                    map_x=i,
                    map_y=0,
                    zone=AREA,
                )
            )
        # a simple ring of exits so wander/adjacency is valid
        for a, b in zip(ROOMS, ROOMS[1:]):
            session.add(Exit(room_id=a, direction="east", target_room_id=b))
            session.add(Exit(room_id=b, direction="west", target_room_id=a))
        # the patrolling guard
        session.add(
            NPC(
                id="guard",
                name="Brass Sentinel",
                description="a patrolling automaton",
                current_room_id="plaza",
                home_room_id="plaza",
                dialogue_tree_id="none",
                ai={"mode": "patrol", "move_every": 1, "route": ROOMS},
                triggers=[
                    {"on": "encounter", "do": {"set_flags": ["greeted_by_guard"]}}
                ],
            )
        )
        # a spawn template (a critter the spawner clones into the zone)
        session.add(
            NPC(
                id="critter_template",
                name="Cog Sprite",
                description="a flicker",
                current_room_id="plaza",
                home_room_id="plaza",
                dialogue_tree_id="none",
            )
        )
        # the player waits at the end of the route
        session.add(
            Player(
                id="p1",
                username="Watcher",
                current_room_id="gate",
                respawn_room_id="gate",
            )
        )
        session.add(PlayerStats(player_id="p1"))
        session.add(
            WorldClock(
                game_epoch=100.0,
                real_epoch=1.0,
                current_season="spring",
                weather="clear",
            )
        )
        session.commit()


@dataclass
class _Rig:
    engine: Engine
    bus: EventBus


def _wire(seed: int = 42) -> _Rig:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    effects_module.get_registry().register(
        EffectDef(key="storm_lashed", modifiers=lambda effect: [])
    )
    _seed(engine)
    bus = EventBus()
    rng = GameRng(seed=seed)
    manager = ConnectionManager()
    meters = MeterService(engine, GameRng())
    effects = EffectService(engine, GameRng())

    # A2 — triggers (guard's encounter, loaded from the NPC's `triggers`)
    triggers = TriggerService(when=dialogue_registry(), do=effect_registry())
    triggers.load(
        [
            Trigger(
                on="encounter",
                entity_type="npc",
                entity_id="guard",
                do={"set_flags": ["greeted_by_guard"]},
            )
        ]
    )
    triggers.register(bus)
    # A3 — the guard's agency loop
    NpcBehaviorService(engine, manager, rng, meters, effects).register(bus)
    # A5 — a spring storm over the town
    WeatherFrontService(
        engine,
        manager,
        rng,
        effects,
        {
            "storms": {
                "squall": {
                    "chance": 1.0,
                    "seasons": ["spring"],
                    "duration_ticks": 2,
                    "travel_ticks": 1,
                    "path": [AREA],
                    "room_effect": "storm_lashed",
                }
            }
        },
    ).register(bus)
    # A6 — keep one critter in the town
    SpawnControllerService(
        engine,
        rng,
        {
            "spawns": {
                "critters": {
                    "area": AREA,
                    "template": "critter_template",
                    "max_count": 1,
                    "every_ticks": 1,
                }
            }
        },
    ).register(bus)
    return _Rig(engine, bus)


def _hour_tick(bus: EventBus) -> None:
    # One in-game hour: the per-tick services (TIME_ADVANCED) and the hourly ones (HOUR_CHANGED).
    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 1.0}), None)
    bus.emit(Event(GameEvent.HOUR_CHANGED, {"hour": 1}), None)


def _guard_room(engine: Engine) -> str:
    with Session(engine) as session:
        guard = session.get(NPC, "guard")
        assert guard is not None
        return guard.current_room_id


def _player_flags(engine: Engine) -> dict[str, object]:
    with Session(engine) as session:
        player = session.get(Player, "p1")
        assert player is not None
        return dict(player.flags)


def _critter_count(engine: Engine) -> int:
    with Session(engine) as session:
        return sum(
            1 for n in session.exec(select(NPC)).all() if n.id.startswith("critters#")
        )


def _room_has_storm(engine: Engine) -> bool:
    with Session(engine) as session:
        return any(
            EffectService(engine, GameRng()).active_for(session, "room", rid)
            for rid in ROOMS
        )


def test_all_phase_a_behaviors_work_together() -> None:
    rig = _wire()

    _hour_tick(
        rig.bus
    )  # guard plaza->market; storm activates over town; critter spawns
    assert _guard_room(rig.engine) == "market"
    assert _room_has_storm(rig.engine)  # A5: storm applied to the zone
    assert _critter_count(rig.engine) == 1  # A6: population topped up
    assert "greeted_by_guard" not in _player_flags(
        rig.engine
    )  # guard not with player yet

    _hour_tick(rig.bus)  # guard market->gate, where the player waits -> encounter fires
    assert _guard_room(rig.engine) == "gate"
    assert (
        _player_flags(rig.engine).get("greeted_by_guard") is True
    )  # A2+A3 from the NPC side


def test_runs_are_deterministic_under_a_fixed_seed() -> None:
    def _run() -> tuple[str, int, bool]:
        rig = _wire(seed=99)
        for _ in range(4):
            _hour_tick(rig.bus)
        return (
            _guard_room(rig.engine),
            _critter_count(rig.engine),
            _player_flags(rig.engine).get("greeted_by_guard") is True,
        )

    assert (
        _run() == _run()
    )  # identical observable state — replay-faithful (all rolls seeded)
