"""Weather and season state transitions."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.world import WorldClock
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
