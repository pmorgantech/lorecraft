"""Zone-specific climate rolls for the weather feature."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.world_context import broadcast_room_async
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.features.weather.handlers import WEATHER_NARRATION
from lorecraft.types import JsonObject


class WeatherChoice(Protocol):
    def __call__(self, seq: Sequence[str]) -> str: ...


class ZoneClimateService:
    """Rolls weather per authored zone climate on ``DAY_CHANGED``."""

    def __init__(
        self,
        game_engine: Engine,
        manager: ConnectionManager,
        rng: GameRng,
        config: JsonObject,
    ) -> None:
        self._engine = game_engine
        self._manager = manager
        self._choice: WeatherChoice = rng.choice
        climates = config.get("climates")
        self._climates: dict[str, JsonObject] = (
            {key: value for key, value in climates.items() if isinstance(value, dict)}
            if isinstance(climates, dict)
            else {}
        )
        self._zone_weather: dict[str, str] = {}

    def register(self, bus: EventBus) -> None:
        if self._climates:
            bus.on(GameEvent.DAY_CHANGED, self._on_day_changed)

    def zone_weather(self, zone: str) -> str | None:
        return self._zone_weather.get(zone)

    def zone_weather_state(self) -> dict[str, str | None]:
        return {zone: self._zone_weather.get(zone) for zone in sorted(self._climates)}

    def configured_zones(self) -> list[str]:
        return sorted(self._climates)

    def set_zone_weather(self, zone: str, weather: str) -> bool:
        if zone not in self._climates:
            raise KeyError(zone)
        previous = self._zone_weather.get(zone)
        self._zone_weather[zone] = weather
        if previous == weather:
            return False
        line = _narration_for(self._climates[zone], weather)
        if line is None:
            return True
        occupied = self._manager.occupied_rooms()
        if not occupied:
            return True
        with Session(self._engine) as session:
            rooms = session.exec(select(Room).where(col(Room.id).in_(occupied))).all()
        for room in rooms:
            if room.zone == zone and not room.indoor:
                broadcast_room_async(self._manager, room.id, line)
        return True

    def _on_day_changed(self, event: Event, ctx: object) -> None:
        del event, ctx
        if not self._climates:
            return
        with Session(self._engine) as session:
            clock = RoomRepo(session).world_clock()
            season = clock.current_season if clock is not None else "spring"
            occupied = self._manager.occupied_rooms()
            rooms = (
                session.exec(select(Room).where(col(Room.id).in_(occupied))).all()
                if occupied
                else []
            )

        by_zone: dict[str, list[Room]] = {}
        for room in rooms:
            if room.zone is not None and not room.indoor:
                by_zone.setdefault(room.zone, []).append(room)

        for zone, spec in self._climates.items():
            previous = self._zone_weather.get(zone)
            weather = roll_zone_weather(spec, season, self._choice)
            if weather is None:
                continue
            self._zone_weather[zone] = weather
            if previous == weather:
                continue
            line = _narration_for(spec, weather)
            if line is None:
                continue
            for room in by_zone.get(zone, []):
                broadcast_room_async(self._manager, room.id, line)


def roll_zone_weather(
    climate: JsonObject, season: str, choice: WeatherChoice
) -> str | None:
    table = climate.get(season, climate.get("default"))
    if not isinstance(table, list) or not table:
        return None
    choices = [weather for weather in table if isinstance(weather, str) and weather]
    if not choices:
        return None
    return choice(tuple(choices))


def _narration_for(climate: JsonObject, weather: str) -> str | None:
    raw = climate.get("narration")
    if isinstance(raw, dict):
        line = raw.get(weather)
        if isinstance(line, str) and line:
            return line
    return WEATHER_NARRATION.get(weather)
