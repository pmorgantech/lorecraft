from lorecraft.features.weather.handlers import apply_daily_weather
from lorecraft.engine.clock.world_clock import (
    SECONDS_PER_HOUR,
    WorldClockRunner,
    advance_clock,
    season_for_day,
)
from lorecraft.db import create_tables
from lorecraft.engine.game.events import EventBus, GameEvent
from lorecraft.engine.models.world import WorldClock
from sqlmodel import Session, create_engine


def test_clock_advance_updates_time_fields_and_boundaries() -> None:
    clock = WorldClock(
        game_epoch=(23 * SECONDS_PER_HOUR) + (59 * 60),
        real_epoch=100.0,
        time_ratio=60.0,
        current_hour=23,
        current_minute=59,
        current_day=1,
        current_season="spring",
        weather="clear",
    )

    advance = advance_clock(clock, now=lambda: 102.0)

    assert advance is not None
    assert advance.hour_changed
    assert advance.day_changed
    assert clock.current_day == 2
    assert clock.current_hour == 0
    assert clock.current_minute == 1


def test_weather_rolls_from_current_season() -> None:
    clock = WorldClock(
        game_epoch=0.0,
        real_epoch=0.0,
        current_season="winter",
        weather="clear",
    )

    changed = apply_daily_weather(clock, lambda options: options[0])

    assert changed
    assert clock.weather == "snow"
    assert season_for_day(31) == "summer"


def test_clock_runner_emits_boundary_events() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    bus = EventBus()
    observed: list[GameEvent] = []
    for event_type in (
        GameEvent.TIME_ADVANCED,
        GameEvent.HOUR_CHANGED,
        GameEvent.DAY_CHANGED,
    ):
        bus.on(event_type, lambda event, ctx: observed.append(event.type))

    with Session(engine) as session:
        session.add(
            WorldClock(
                game_epoch=(23 * SECONDS_PER_HOUR) + (59 * 60),
                real_epoch=100.0,
                time_ratio=60.0,
                current_hour=23,
                current_minute=59,
                current_day=1,
                current_season="spring",
                weather="clear",
            )
        )
        session.commit()

    runner = WorldClockRunner(
        game_engine=engine,
        bus=bus,
        time_ratio=60.0,
        now=lambda: 102.0,
    )
    runner.tick()

    assert observed == [
        GameEvent.TIME_ADVANCED,
        GameEvent.HOUR_CHANGED,
        GameEvent.DAY_CHANGED,
    ]
