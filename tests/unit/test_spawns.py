"""A6 — area spawn/respawn controllers (features/spawns).

A spawner tops a zone's population back up to `max_count` clones of a template NPC. See
`docs/scripting_engine_design.md` §3.4.
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.world import NPC, Room
from lorecraft.features.spawns.service import SpawnControllerService
from lorecraft.types import JsonObject

AREA = "whisperwood"
SPAWN = "sprite"


@pytest.fixture
def engine() -> Engine:  # type: ignore[misc]
    eng = create_engine("sqlite://")
    create_tables(game_engine=eng, audit_engine=create_engine("sqlite://"))
    with Session(eng) as session:
        session.add(
            Room(id="w1", name="Glade", description="d", map_x=0, map_y=0, area_id=AREA)
        )
        session.add(
            Room(
                id="w2", name="Thicket", description="d", map_x=1, map_y=0, area_id=AREA
            )
        )
        session.add(
            NPC(
                id="sprite_template",
                name="Wood Sprite",
                description="a flicker of light",
                current_room_id="w1",
                home_room_id="w1",
                dialogue_tree_id="none",
                ai={"mode": "wander", "move_every": 2},
            )
        )
        session.commit()
    return eng


def _config(max_count: int = 2, every_ticks: int = 1) -> JsonObject:
    return {
        "spawns": {
            SPAWN: {
                "area": AREA,
                "template": "sprite_template",
                "max_count": max_count,
                "every_ticks": every_ticks,
            }
        }
    }


def _service(
    engine: Engine, bus: EventBus, config: JsonObject
) -> SpawnControllerService:
    service = SpawnControllerService(engine, GameRng(seed=5), config)
    service.register(bus)
    return service


def _tick(bus: EventBus) -> None:
    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 1.0}), None)


def _clones(engine: Engine) -> list[NPC]:
    with Session(engine) as session:
        return [
            n for n in session.exec(select(NPC)).all() if n.id.startswith(f"{SPAWN}#")
        ]


def test_spawns_up_to_max_count(engine: Engine) -> None:
    bus = EventBus()
    _service(engine, bus, _config(max_count=2))
    _tick(bus)
    clones = _clones(engine)
    assert len(clones) == 2
    assert all(c.current_room_id in {"w1", "w2"} for c in clones)
    assert all(c.name == "Wood Sprite" for c in clones)


def test_does_not_over_spawn(engine: Engine) -> None:
    bus = EventBus()
    _service(engine, bus, _config(max_count=2))
    _tick(bus)
    _tick(bus)
    _tick(bus)
    assert len(_clones(engine)) == 2


def test_repopulates_after_removal(engine: Engine) -> None:
    bus = EventBus()
    _service(engine, bus, _config(max_count=2))
    _tick(bus)
    assert len(_clones(engine)) == 2
    # A clone is slain / removed.
    with Session(engine) as session:
        victim = _clones(engine)[0]
        session.delete(session.get(NPC, victim.id))
        session.commit()
    assert len(_clones(engine)) == 1
    _tick(bus)
    assert len(_clones(engine)) == 2  # topped back up


def test_every_ticks_gates_spawning(engine: Engine) -> None:
    bus = EventBus()
    _service(engine, bus, _config(max_count=2, every_ticks=3))
    _tick(bus)
    _tick(bus)
    assert _clones(engine) == []  # not yet
    _tick(bus)
    assert len(_clones(engine)) == 2


def test_cloned_ai_is_inherited(engine: Engine) -> None:
    bus = EventBus()
    _service(engine, bus, _config(max_count=1))
    _tick(bus)
    clone = _clones(engine)[0]
    assert clone.ai == {"mode": "wander", "move_every": 2}
