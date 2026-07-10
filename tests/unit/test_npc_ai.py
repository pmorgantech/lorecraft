"""A3 — the autonomous NPC agency loop (features/npc_ai).

NPCs with an `ai` config move on `TIME_ADVANCED` (wander/patrol), emit `NPC_MOVED`, and — when
one walks into a room where a player stands — fire that NPC's `encounter` triggers. See
`docs/scripting_engine_design.md` §3.2.
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import NPC, Exit, Room
from lorecraft.engine.scripting.triggers import Trigger, TriggerService
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.npc.dialogue_conditions import get_registry as dialogue_registry
from lorecraft.features.npc.side_effects import get_registry as effect_registry
from lorecraft.features.npc_ai.service import NpcBehaviorService

ROOM_A = "plaza"
ROOM_B = "market"


@pytest.fixture
def engine() -> Engine:  # type: ignore[misc]
    eng = create_engine("sqlite://")
    create_tables(game_engine=eng, audit_engine=create_engine("sqlite://"))
    with Session(eng) as session:
        session.add(
            Room(
                id=ROOM_A,
                name="Plaza",
                description="d",
                map_x=0,
                map_y=0,
                area_id="town",
            )
        )
        session.add(
            Room(
                id=ROOM_B,
                name="Market",
                description="d",
                map_x=1,
                map_y=0,
                area_id="town",
            )
        )
        session.add(Exit(room_id=ROOM_A, direction="east", target_room_id=ROOM_B))
        session.add(Exit(room_id=ROOM_B, direction="west", target_room_id=ROOM_A))
        session.commit()
    return eng


def _add_npc(engine: Engine, ai: dict[str, object], *, room: str = ROOM_A) -> None:
    with Session(engine) as session:
        session.add(
            NPC(
                id="rover",
                name="Rover",
                description="a wanderer",
                current_room_id=room,
                home_room_id=room,
                dialogue_tree_id="none",
                ai=ai,
            )
        )
        session.commit()


def _service(
    engine: Engine, bus: EventBus, rng: GameRng | None = None
) -> NpcBehaviorService:
    bind = engine
    service = NpcBehaviorService(
        engine,
        ConnectionManager(),
        rng or GameRng(seed=3),
        MeterService(bind, GameRng()),
        EffectService(bind, GameRng()),
    )
    service.register(bus)
    return service


def _npc_room(engine: Engine) -> str:
    with Session(engine) as session:
        npc = session.get(NPC, "rover")
        assert npc is not None
        return npc.current_room_id


def _tick(bus: EventBus) -> None:
    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 1.0}), None)


def test_wander_moves_to_the_only_exit(engine: Engine) -> None:
    _add_npc(engine, {"mode": "wander", "move_every": 1})
    bus = EventBus()
    moved: list[tuple[str, str]] = []
    bus.on(
        GameEvent.NPC_MOVED,
        lambda event, ctx: moved.append(
            (str(event.payload["from_room_id"]), str(event.payload["to_room_id"]))
        ),
    )
    _service(engine, bus)
    _tick(bus)
    assert _npc_room(engine) == ROOM_B
    assert moved == [(ROOM_A, ROOM_B)]


def test_move_every_gates_movement(engine: Engine) -> None:
    _add_npc(engine, {"mode": "wander", "move_every": 3})
    bus = EventBus()
    _service(engine, bus)
    _tick(bus)
    _tick(bus)
    assert _npc_room(engine) == ROOM_A  # not yet
    _tick(bus)
    assert _npc_room(engine) == ROOM_B  # third tick moves


def test_patrol_follows_route_and_loops(engine: Engine) -> None:
    _add_npc(engine, {"mode": "patrol", "move_every": 1, "route": [ROOM_A, ROOM_B]})
    bus = EventBus()
    _service(engine, bus)
    _tick(bus)
    assert _npc_room(engine) == ROOM_B
    _tick(bus)
    assert _npc_room(engine) == ROOM_A  # looped back


def test_wander_confined_to_area(engine: Engine) -> None:
    # Add a third room in a different area reachable from A; wander must not pick it.
    with Session(engine) as session:
        session.add(
            Room(
                id="cave",
                name="Cave",
                description="d",
                map_x=0,
                map_y=1,
                area_id="wild",
            )
        )
        session.add(Exit(room_id=ROOM_A, direction="down", target_room_id="cave"))
        session.commit()
    _add_npc(engine, {"mode": "wander", "move_every": 1, "area": "town"})
    bus = EventBus()
    _service(engine, bus)
    _tick(bus)
    assert _npc_room(engine) == ROOM_B  # only the town-area exit


def test_npc_moving_into_player_fires_encounter_trigger(engine: Engine) -> None:
    # Rover patrols A->B; a player waits in B with Rover carrying an encounter trigger.
    _add_npc(engine, {"mode": "patrol", "move_every": 1, "route": [ROOM_A, ROOM_B]})
    with Session(engine) as session:
        session.add(
            Player(
                id="p1",
                username="Waiter",
                current_room_id=ROOM_B,
                respawn_room_id=ROOM_B,
            )
        )
        session.add(PlayerStats(player_id="p1"))
        session.commit()

    bus = EventBus()
    triggers = TriggerService(when=dialogue_registry(), do=effect_registry())
    triggers.load(
        [
            Trigger(
                on="encounter",
                entity_type="npc",
                entity_id="rover",
                do={"set_flags": ["met_rover"]},
            )
        ]
    )
    triggers.register(bus)
    _service(engine, bus)

    _tick(bus)  # Rover walks A -> B, where the player stands

    assert _npc_room(engine) == ROOM_B
    with Session(engine) as session:
        player = session.get(Player, "p1")
        assert player is not None
        assert player.flags.get("met_rover") is True
