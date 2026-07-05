"""Persistent world clock and async background loop."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import time

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.clock.weather import season_for_day
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.models.world import WorldClock
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.types import JsonObject

SECONDS_PER_DAY = 24 * 60 * 60
SECONDS_PER_HOUR = 60 * 60
START_HOUR = 8


@dataclass(frozen=True)
class ClockAdvance:
    previous_epoch: float
    current_epoch: float
    previous_hour: int
    current_hour: int
    previous_day: int
    current_day: int
    previous_season: str
    current_season: str

    @property
    def hour_changed(self) -> bool:
        return self.previous_hour != self.current_hour

    @property
    def day_changed(self) -> bool:
        return self.previous_day != self.current_day

    @property
    def season_changed(self) -> bool:
        return self.previous_season != self.current_season


@dataclass(frozen=True)
class ClockEventContext:
    game_engine: Engine
    bus: EventBus


class WorldClockRunner:
    def __init__(
        self,
        *,
        game_engine: Engine,
        bus: EventBus,
        time_ratio: float,
        tick_seconds: float = 1.0,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.game_engine = game_engine
        self.bus = bus
        self.time_ratio = time_ratio
        self.tick_seconds = tick_seconds
        self._now = now
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self.tick()

    def initialize(self) -> None:
        with Session(self.game_engine) as session:
            clock = ensure_world_clock(session, self.time_ratio, now=self._now)
            advance = fast_forward_clock(clock, now=self._now)
            session.commit()

        if advance is not None:
            self._emit_advance_events(advance)

    def tick(self) -> ClockAdvance | None:
        with Session(self.game_engine) as session:
            clock = RoomRepo(session).world_clock()
            if clock is None:
                clock = ensure_world_clock(session, self.time_ratio, now=self._now)
            advance = advance_clock(clock, now=self._now)
            session.commit()

        if advance is not None:
            self._emit_advance_events(advance)
        return advance

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.tick_seconds)
            self.tick()

    def _emit_advance_events(self, advance: ClockAdvance) -> None:
        ctx = ClockEventContext(game_engine=self.game_engine, bus=self.bus)
        payload: JsonObject = {
            "previous_epoch": advance.previous_epoch,
            "current_epoch": advance.current_epoch,
        }
        self.bus.emit(Event(GameEvent.TIME_ADVANCED, payload), ctx)

        if advance.hour_changed:
            self.bus.emit(
                Event(
                    GameEvent.HOUR_CHANGED,
                    {
                        **payload,
                        "previous_hour": advance.previous_hour,
                        "hour": advance.current_hour,
                    },
                ),
                ctx,
            )
        if advance.day_changed:
            self.bus.emit(
                Event(
                    GameEvent.DAY_CHANGED,
                    {
                        **payload,
                        "previous_day": advance.previous_day,
                        "day": advance.current_day,
                    },
                ),
                ctx,
            )
        if advance.season_changed:
            self.bus.emit(
                Event(
                    GameEvent.SEASON_CHANGED,
                    {
                        **payload,
                        "previous_season": advance.previous_season,
                        "season": advance.current_season,
                    },
                ),
                ctx,
            )


def ensure_world_clock(
    session: Session, time_ratio: float, *, now: Callable[[], float] = time.time
) -> WorldClock:
    clock = RoomRepo(session).world_clock()
    if clock is not None:
        return clock

    clock = WorldClock(
        game_epoch=START_HOUR * SECONDS_PER_HOUR,
        real_epoch=now(),
        time_ratio=time_ratio,
    )
    apply_clock_fields(clock)
    session.add(clock)
    return clock


def fast_forward_clock(
    clock: WorldClock, *, now: Callable[[], float] = time.time
) -> ClockAdvance | None:
    if clock.paused:
        clock.real_epoch = now()
        return None
    return advance_clock(clock, now=now)


def advance_clock(
    clock: WorldClock, *, now: Callable[[], float] = time.time
) -> ClockAdvance | None:
    current_real_epoch = now()
    elapsed_real_seconds = current_real_epoch - clock.real_epoch
    if elapsed_real_seconds <= 0 or clock.paused:
        clock.real_epoch = current_real_epoch
        return None

    previous_epoch = clock.game_epoch
    previous_hour = clock.current_hour
    previous_day = clock.current_day
    previous_season = clock.current_season

    clock.game_epoch += elapsed_real_seconds * clock.time_ratio
    clock.real_epoch = current_real_epoch
    apply_clock_fields(clock)

    return ClockAdvance(
        previous_epoch=previous_epoch,
        current_epoch=clock.game_epoch,
        previous_hour=previous_hour,
        current_hour=clock.current_hour,
        previous_day=previous_day,
        current_day=clock.current_day,
        previous_season=previous_season,
        current_season=clock.current_season,
    )


def apply_clock_fields(clock: WorldClock) -> None:
    day_index = int(clock.game_epoch // SECONDS_PER_DAY)
    seconds_in_day = int(clock.game_epoch % SECONDS_PER_DAY)
    clock.current_day = day_index + 1
    clock.current_hour = seconds_in_day // SECONDS_PER_HOUR
    clock.current_minute = (seconds_in_day % SECONDS_PER_HOUR) // 60
    clock.current_season = season_for_day(clock.current_day)
