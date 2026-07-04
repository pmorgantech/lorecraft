"""Weather and season state transitions."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.game.events import Event, EventBus, GameEvent
from lorecraft.game.rng import GameRng
from lorecraft.models.world import WorldClock
from lorecraft.repos.room_repo import RoomRepo

SEASONS = ("spring", "summer", "autumn", "winter")
DAYS_PER_SEASON = 30
WEATHER_TABLE: dict[str, tuple[str, ...]] = {
    "spring": ("clear", "light_rain", "overcast", "clear", "clear"),
    "summer": ("clear", "clear", "hot", "clear", "thunderstorm"),
    "autumn": ("overcast", "heavy_rain", "clear", "fog", "clear"),
    "winter": ("snow", "clear", "blizzard", "fog", "clear"),
}


class WeatherChoice(Protocol):
    def __call__(self, seq: tuple[str, ...]) -> str: ...


def season_for_day(day: int) -> str:
    season_index = ((max(day, 1) - 1) // DAYS_PER_SEASON) % len(SEASONS)
    return SEASONS[season_index]


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
    *,
    rng: GameRng,
) -> None:
    choice: WeatherChoice = rng.choice

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
