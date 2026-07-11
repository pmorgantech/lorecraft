"""Weather and season state transitions."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.world_context import broadcast_room_async
from lorecraft.engine.models.world import Room, WorldClock
from lorecraft.engine.repos.room_repo import RoomRepo

WEATHER_TABLE: dict[str, tuple[str, ...]] = {
    "spring": ("clear", "light_rain", "overcast", "clear", "clear"),
    "summer": ("clear", "clear", "hot", "clear", "thunderstorm"),
    "autumn": ("overcast", "heavy_rain", "clear", "fog", "clear"),
    "winter": ("snow", "clear", "blizzard", "fog", "clear"),
}

# Weather that makes exposure a real concern without adequate warmth (Sprint
# 27.2) -- gives worn clothing (warmth_bonus items) a non-combat purpose.
COLD_WEATHERS = frozenset({"snow", "blizzard", "fog"})

# The narration voice that announces an ambient weather transition to everyone
# (Sprint 63). Keyed on the *new* weather (absolute onset phrasing), one entry
# per weather key the roll table / admin console can produce.
WEATHER_NARRATION: dict[str, str] = {
    "clear": "The clouds part and the sky clears.",
    "light_rain": "A light rain begins to fall.",
    "heavy_rain": "The sky opens up and rain hammers down.",
    "overcast": "The sky greys over, heavy and overcast.",
    "hot": "The air turns hot and still.",
    "thunderstorm": "Thunder rumbles as a storm rolls in.",
    "fog": "A thick fog settles over the land.",
    "snow": "Snow begins to drift down from a leaden sky.",
    "blizzard": "A howling blizzard sweeps in, thick with snow.",
}


def weather_change_line(previous_weather: str, weather: str) -> str | None:
    """The narration line for a weather transition, or ``None`` when nothing changed.

    Returns ``None`` if the weather is unchanged or the new weather has no registered
    narration, so callers can broadcast unconditionally without announcing a non-event.
    """
    if weather == previous_weather:
        return None
    return WEATHER_NARRATION.get(weather)


def narrate_weather_outdoors(
    manager: ConnectionManager, game_engine: Engine, line: str
) -> None:
    """Announce an ambient weather line to every occupied *outdoor* room.

    Players sheltered indoors (``Room.indoor``) can't see the sky, so weather narration is
    filtered to outdoor rooms that currently have an audience — no point querying or pushing
    to empty rooms either.
    """
    occupied = manager.occupied_rooms()
    if not occupied:
        return
    with Session(game_engine) as session:
        indoor = set(
            session.exec(
                select(Room.id).where(col(Room.id).in_(occupied), col(Room.indoor))
            ).all()
        )
    for room_id in occupied:
        if room_id not in indoor:
            broadcast_room_async(manager, room_id, line)


class WeatherChoice(Protocol):
    def __call__(self, seq: tuple[str, ...]) -> str: ...


def roll_weather(clock: WorldClock, choice: WeatherChoice) -> str:
    return choice(WEATHER_TABLE[clock.current_season])


def apply_daily_weather(clock: WorldClock, choice: WeatherChoice) -> bool:
    next_weather = roll_weather(clock, choice)
    if next_weather == clock.weather:
        return False
    clock.weather = next_weather
    return True


def register_weather_handlers(
    bus: EventBus,
    game_engine: Engine,
    manager: ConnectionManager,
    *,
    rng: GameRng,
) -> None:
    choice: WeatherChoice = rng.choice

    def on_weather_changed(event: Event, ctx: object) -> None:
        """Announce an ambient weather transition to every connected player.

        Fires for both the automatic daily roll (``on_day_changed`` below) and manual
        admin ``set_weather`` changes — both emit ``WEATHER_CHANGED``. Best-effort: a
        dropped narration never affects the committed weather state.
        """
        del ctx
        previous = event.payload.get("previous_weather")
        weather = event.payload.get("weather")
        if not isinstance(previous, str) or not isinstance(weather, str):
            return
        line = weather_change_line(previous, weather)
        if line is not None:
            narrate_weather_outdoors(manager, game_engine, line)

    bus.on(GameEvent.WEATHER_CHANGED, on_weather_changed)

    def on_day_changed(event: Event, ctx: object) -> None:
        del event
        with Session(game_engine) as session:
            clock = RoomRepo(session).world_clock()
            if clock is None:
                return
            previous_weather = clock.weather
            if not apply_daily_weather(clock, choice):
                return
            weather = clock.weather
            season = clock.current_season
            day = clock.current_day
            session.commit()

        bus.emit(
            Event(
                GameEvent.WEATHER_CHANGED,
                {
                    "previous_weather": previous_weather,
                    "weather": weather,
                    "season": season,
                    "day": day,
                },
            ),
            ctx,
        )

    bus.on(GameEvent.DAY_CHANGED, on_day_changed)
