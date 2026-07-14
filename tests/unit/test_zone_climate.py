"""Zone-local climate rolls for weather."""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.world import Room, WorldClock
from lorecraft.features.weather.climate import ZoneClimateService, roll_zone_weather
from lorecraft.types import JsonObject


def _engine() -> Engine:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        session.add(
            Room(
                id="wood",
                name="Wood",
                description="d",
                map_x=0,
                map_y=0,
                zone="whisperwood",
            )
        )
        session.add(
            Room(
                id="vault",
                name="Vault",
                description="d",
                map_x=1,
                map_y=0,
                zone="whisperwood",
                indoor=True,
            )
        )
        session.add(
            Room(
                id="city",
                name="City",
                description="d",
                map_x=2,
                map_y=0,
                zone="cogsworth",
            )
        )
        session.add(WorldClock(game_epoch=0.0, real_epoch=0.0, current_season="spring"))
        session.commit()
    return engine


def _config() -> JsonObject:
    return {
        "climates": {
            "whisperwood": {
                "spring": ["fog"],
                "narration": {"fog": "Mist gathers."},
            },
            "cogsworth": {
                "spring": ["overcast"],
                "narration": {"overcast": "Clouds settle."},
            },
        }
    }


def test_roll_zone_weather_uses_seasonal_weight_table() -> None:
    assert (
        roll_zone_weather(
            {"spring": ["fog", "light_rain"], "default": ["clear"]},
            "spring",
            lambda seq: seq[0],
        )
        == "fog"
    )


def test_zone_climate_broadcasts_only_to_matching_outdoor_zone(monkeypatch) -> None:
    engine = _engine()
    manager = ConnectionManager()
    manager.move_player("p-wood", None, "wood")
    manager.move_player("p-vault", None, "vault")
    manager.move_player("p-city", None, "city")
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "lorecraft.features.weather.climate.broadcast_room_async",
        lambda _manager, room_id, text: seen.append((room_id, text)),
    )
    service = ZoneClimateService(engine, manager, GameRng(seed=1), _config())
    bus = EventBus()
    service.register(bus)

    bus.emit(Event(GameEvent.DAY_CHANGED, {"day": 2}), None)

    assert service.zone_weather("whisperwood") == "fog"
    assert service.zone_weather("cogsworth") == "overcast"
    assert ("wood", "Mist gathers.") in seen
    assert ("city", "Clouds settle.") in seen
    assert all(room_id != "vault" for room_id, _text in seen)
