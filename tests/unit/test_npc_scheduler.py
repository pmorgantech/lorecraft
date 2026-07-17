from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.models.world import NPC, Room
from lorecraft.features.npc.scheduler import NpcScheduler


def _engine() -> Engine:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        session.add(
            Room(
                id="square",
                name="Square",
                description="A busy square.",
                map_x=0,
                map_y=0,
            )
        )
        session.add(
            Room(
                id="barracks",
                name="Barracks",
                description="A watch barracks.",
                map_x=1,
                map_y=0,
            )
        )
        session.commit()
    return engine


def _npc(engine: Engine) -> NPC:
    with Session(engine) as session:
        npc = session.get(NPC, "holt")
        assert npc is not None
        return npc


def test_schedule_entry_applies_location_behavior_and_ai() -> None:
    engine = _engine()
    with Session(engine) as session:
        session.add(
            NPC(
                id="holt",
                name="Watchman Holt",
                description="A city watchman.",
                current_room_id="square",
                home_room_id="square",
                dialogue_tree_id="none",
                behavior="defensive",
                ai={},
                schedule=[
                    {
                        "game_hour": 20,
                        "target_room_id": "barracks",
                        "behavior": "alert",
                        "ai": {
                            "mode": "patrol",
                            "move_every": 2,
                            "route": ["square", "barracks"],
                        },
                    }
                ],
            )
        )
        session.commit()

    bus = EventBus()
    NpcScheduler(engine).register(bus)
    bus.emit(Event(GameEvent.HOUR_CHANGED, {"hour": 20}), None)

    npc = _npc(engine)
    assert npc.current_room_id == "barracks"
    assert npc.behavior == "alert"
    assert npc.ai == {
        "mode": "patrol",
        "move_every": 2,
        "route": ["square", "barracks"],
    }


def test_schedule_entry_can_change_behavior_and_clear_ai_without_moving() -> None:
    engine = _engine()
    with Session(engine) as session:
        session.add(
            NPC(
                id="holt",
                name="Watchman Holt",
                description="A city watchman.",
                current_room_id="square",
                home_room_id="square",
                dialogue_tree_id="none",
                behavior="alert",
                ai={"mode": "wander", "move_every": 1},
                schedule=[
                    {
                        "game_hour": 8,
                        "behavior": "defensive",
                        "ai": {},
                    }
                ],
            )
        )
        session.commit()

    bus = EventBus()
    NpcScheduler(engine).register(bus)
    bus.emit(Event(GameEvent.HOUR_CHANGED, {"hour": 8}), None)

    npc = _npc(engine)
    assert npc.current_room_id == "square"
    assert npc.behavior == "defensive"
    assert npc.ai == {}
