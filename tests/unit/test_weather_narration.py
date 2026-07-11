"""Ambient weather narration: WEATHER_CHANGED announces a line to *outdoor* players.

The automatic daily roll and the admin `set_weather` console both emit WEATHER_CHANGED;
`register_weather_handlers` wires a narration voice that broadcasts the transition to every
occupied outdoor room. Players sheltered indoors (`Room.indoor`) don't see the sky change.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.engine import Engine, create_engine
from sqlmodel import Session

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.world import Room
from lorecraft.features.weather.handlers import (
    WEATHER_NARRATION,
    WEATHER_TABLE,
    register_weather_handlers,
    weather_change_line,
)
from lorecraft.types import JsonObject


class _FakeSocket:
    """JsonWebSocket stand-in that records everything sent to it."""

    def __init__(self) -> None:
        self.sent: list[JsonObject] = []

    async def accept(self) -> None:
        pass

    async def send_json(self, data: JsonObject) -> None:
        self.sent.append(data)


def test_change_line_maps_the_new_weather() -> None:
    assert weather_change_line("clear", "light_rain") == "A light rain begins to fall."


def test_change_line_is_none_when_weather_is_unchanged() -> None:
    assert weather_change_line("fog", "fog") is None


def test_change_line_is_none_for_unknown_weather() -> None:
    assert weather_change_line("clear", "meteor_shower") is None


def test_every_rollable_weather_has_a_narration_line() -> None:
    rollable = {weather for seq in WEATHER_TABLE.values() for weather in seq}
    missing = rollable - set(WEATHER_NARRATION)
    assert not missing, f"weather with no narration line: {sorted(missing)}"


def _engine_with_rooms() -> Engine:
    eng = create_engine("sqlite://")
    create_tables(game_engine=eng, audit_engine=create_engine("sqlite://"))
    with Session(eng) as session:
        session.add(Room(id="plaza", name="Plaza", description="d", map_x=0, map_y=0))
        session.add(
            Room(
                id="vault",
                name="Vault",
                description="d",
                map_x=1,
                map_y=0,
                indoor=True,
            )
        )
        session.commit()
    return eng


def _emit_weather_change(
    engine: Engine, manager: ConnectionManager, previous: str, weather: str
) -> None:
    bus = EventBus()
    register_weather_handlers(bus, engine, manager, rng=GameRng(1))
    bus.emit(
        Event(
            GameEvent.WEATHER_CHANGED,
            {
                "previous_weather": previous,
                "weather": weather,
                "season": "spring",
                "day": 1,
            },
        ),
        None,
    )


def test_weather_change_reaches_outdoor_players_but_not_indoors() -> None:
    async def run() -> tuple[list[JsonObject], list[JsonObject]]:
        engine = _engine_with_rooms()
        manager = ConnectionManager()
        outdoor = _FakeSocket()
        indoor = _FakeSocket()
        await manager.connect("p-out", outdoor, room_id="plaza")
        await manager.connect("p-in", indoor, room_id="vault")
        _emit_weather_change(engine, manager, "clear", "light_rain")
        await asyncio.sleep(0.05)  # let the fire-and-forget broadcast tasks run
        return outdoor.sent, indoor.sent

    outdoor_sent, indoor_sent = asyncio.run(run())
    assert [m["content"] for m in outdoor_sent] == ["A light rain begins to fall."]
    assert indoor_sent == []


def test_unchanged_weather_is_not_announced() -> None:
    async def run() -> list[JsonObject]:
        engine = _engine_with_rooms()
        manager = ConnectionManager()
        outdoor = _FakeSocket()
        await manager.connect("p-out", outdoor, room_id="plaza")
        _emit_weather_change(engine, manager, "fog", "fog")
        await asyncio.sleep(0.05)
        return outdoor.sent

    assert asyncio.run(run()) == []
