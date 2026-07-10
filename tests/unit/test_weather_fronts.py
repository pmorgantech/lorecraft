"""A5 — traveling weather fronts + narrate_zone.

A storm rolls (seeded), applies a room effect over a zone, travels zone->zone, and expires,
cleaning up. See `docs/scripting_engine_design.md` §A.4.
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.engine.game import effects as effects_module
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.effects import EffectDef
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.world import Room, WorldClock
from lorecraft.engine.services.effects import EffectService
from lorecraft.features.weather.fronts import WeatherFrontService
from lorecraft.types import JsonObject

Z1 = "whisperwood"
Z2 = "port_veridian"


@pytest.fixture(autouse=True)
def _storm_effect() -> None:
    effects_module.get_registry().register(
        EffectDef(key="storm_lashed", modifiers=lambda effect: [])
    )


@pytest.fixture
def engine() -> Engine:  # type: ignore[misc]
    eng = create_engine("sqlite://")
    create_tables(game_engine=eng, audit_engine=create_engine("sqlite://"))
    with Session(eng) as session:
        session.add(
            Room(id="w1", name="Glade", description="d", map_x=0, map_y=0, area_id=Z1)
        )
        session.add(
            Room(id="w2", name="Thicket", description="d", map_x=1, map_y=0, area_id=Z1)
        )
        session.add(
            Room(id="p1", name="Docks", description="d", map_x=2, map_y=0, area_id=Z2)
        )
        session.add(
            WorldClock(
                game_epoch=100.0,
                real_epoch=1.0,
                current_season="spring",
                weather="clear",
            )
        )
        session.commit()
    return eng


def _config(chance: float = 1.0) -> JsonObject:
    return {
        "storms": {
            "fey_tempest": {
                "chance": chance,
                "seasons": ["spring"],
                "duration_ticks": 3,
                "travel_ticks": 1,
                "path": [Z1, Z2],
                "room_effect": "storm_lashed",
                "on_enter": "The sky darkens.",
                "on_leave": "The storm passes.",
            }
        }
    }


def _service(engine: Engine, bus: EventBus, config: JsonObject) -> WeatherFrontService:
    service = WeatherFrontService(
        engine,
        ConnectionManager(),
        GameRng(seed=1),
        EffectService(engine, GameRng()),
        config,
    )
    service.register(bus)
    return service


def _hour(bus: EventBus) -> None:
    bus.emit(Event(GameEvent.HOUR_CHANGED, {"hour": 1}), None)


def _room_effects(engine: Engine, room_id: str) -> list[str]:
    with Session(engine) as session:
        return [
            e.effect_key
            for e in EffectService(engine, GameRng()).active_for(
                session, "room", room_id
            )
        ]


def test_storm_applies_effect_over_the_first_zone(engine: Engine) -> None:
    bus = EventBus()
    _service(engine, bus, _config())
    _hour(bus)
    assert _room_effects(engine, "w1") == ["storm_lashed"]
    assert _room_effects(engine, "w2") == ["storm_lashed"]
    assert _room_effects(engine, "p1") == []  # zone 2 not yet


def test_front_travels_to_the_next_zone(engine: Engine) -> None:
    bus = EventBus()
    _service(engine, bus, _config())
    _hour(bus)  # activate over Z1
    _hour(bus)  # travel to Z2
    assert _room_effects(engine, "w1") == []  # cleaned up on leave
    assert _room_effects(engine, "p1") == ["storm_lashed"]


def test_expiry_cleans_up_before_reactivation(engine: Engine) -> None:
    # A single-zone always-on storm: expire must remove the old room effect before the next
    # activation re-applies it, so effects never accumulate across cycles.
    config: JsonObject = {
        "storms": {
            "drizzle": {
                "chance": 1.0,
                "duration_ticks": 2,
                "travel_ticks": 1,
                "path": [Z1],
                "room_effect": "storm_lashed",
            }
        }
    }
    bus = EventBus()
    _service(engine, bus, config)
    for _ in range(6):
        _hour(bus)
    # At most one active storm_lashed per room — no leak across expire/re-roll cycles.
    assert len(_room_effects(engine, "w1")) <= 1
    assert len(_room_effects(engine, "w2")) <= 1


def test_storm_does_not_roll_out_of_season(engine: Engine) -> None:
    with Session(engine) as session:
        clock = session.exec(select(WorldClock)).first()
        assert clock is not None
        clock.current_season = "winter"
        session.commit()
    bus = EventBus()
    _service(engine, bus, _config(chance=1.0))
    _hour(bus)
    assert _room_effects(engine, "w1") == []  # spring-only storm, it's winter


def test_zero_chance_never_activates(engine: Engine) -> None:
    bus = EventBus()
    _service(engine, bus, _config(chance=0.0))
    _hour(bus)
    assert _room_effects(engine, "w1") == []
