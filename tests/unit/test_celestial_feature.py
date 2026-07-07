"""Sprint 54.2: celestial feature — transition handlers + condition gates."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.clock.celestial import DAYS_PER_MOON_PHASE, HOURS_PER_TIDE
from lorecraft.engine.game.command_conditions import get_registry as command_registry
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.models.world import WorldClock
from lorecraft.features.celestial.conditions import register as register_conditions
from lorecraft.features.celestial.handlers import register_celestial_handlers
from lorecraft.features.npc.dialogue_conditions import (
    get_registry as dialogue_registry,
)
from tests.unit.test_marks_service import _ctx, _seed


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        yield session


def _capture(bus: EventBus, event_type: GameEvent) -> list[Event]:
    seen: list[Event] = []
    bus.on(event_type, lambda event, ctx: seen.append(event))
    return seen


class TestTransitionHandlers:
    def test_moon_phase_change_emitted_on_boundary_day(self) -> None:
        bus = EventBus()
        register_celestial_handlers(bus)
        seen = _capture(bus, GameEvent.MOON_PHASE_CHANGED)

        boundary = DAYS_PER_MOON_PHASE  # last "new" day → first "waxing_crescent"
        bus.emit(
            Event(
                GameEvent.DAY_CHANGED,
                {"previous_day": boundary, "day": boundary + 1},
            ),
            object(),
        )

        assert len(seen) == 1
        assert seen[0].payload["previous_phase"] == "new"
        assert seen[0].payload["phase"] == "waxing_crescent"

    def test_no_moon_event_within_a_phase(self) -> None:
        bus = EventBus()
        register_celestial_handlers(bus)
        seen = _capture(bus, GameEvent.MOON_PHASE_CHANGED)

        bus.emit(Event(GameEvent.DAY_CHANGED, {"previous_day": 1, "day": 2}), object())

        assert seen == []

    def test_tide_change_emitted_on_boundary_hour(self) -> None:
        bus = EventBus()
        register_celestial_handlers(bus)
        seen = _capture(bus, GameEvent.TIDE_CHANGED)

        bus.emit(
            Event(
                GameEvent.HOUR_CHANGED,
                {"previous_hour": HOURS_PER_TIDE - 1, "hour": HOURS_PER_TIDE},
            ),
            object(),
        )

        assert len(seen) == 1
        assert seen[0].payload["previous_tide"] == "low"
        assert seen[0].payload["tide"] == "high"

    def test_no_tide_event_within_a_state(self) -> None:
        bus = EventBus()
        register_celestial_handlers(bus)
        seen = _capture(bus, GameEvent.TIDE_CHANGED)

        bus.emit(
            Event(GameEvent.HOUR_CHANGED, {"previous_hour": 0, "hour": 1}), object()
        )

        assert seen == []


class TestConditionGates:
    def _gated_ctx(self, session: Session, *, day: int = 1, hour: int = 0):
        player = _seed(session)
        ctx = _ctx(session, player)
        ctx.clock = WorldClock(
            game_epoch=0.0,
            real_epoch=0.0,
            current_hour=hour,
            current_day=day,
        )
        return ctx

    def test_moon_phase_is_command_condition(self, session: Session) -> None:
        register_conditions()
        registry = command_registry()
        full_day = 4 * DAYS_PER_MOON_PHASE + 1  # first "full" day

        ctx = self._gated_ctx(session, day=full_day)
        assert registry.evaluate("moon_phase_is:full", ctx).allowed is True

        ctx.clock.current_day = 1
        blocked = registry.evaluate("moon_phase_is:full", ctx)
        assert blocked.allowed is False
        assert blocked.reason is not None and "full moon" in blocked.reason

    def test_tide_is_command_condition(self, session: Session) -> None:
        register_conditions()
        registry = command_registry()

        ctx = self._gated_ctx(session, hour=0)
        assert registry.evaluate("tide_is:low", ctx).allowed is True
        assert registry.evaluate("tide_is:high", ctx).allowed is False

    def test_unknown_state_and_missing_clock_fail_closed(
        self, session: Session
    ) -> None:
        register_conditions()
        registry = command_registry()

        ctx = self._gated_ctx(session)
        assert registry.evaluate("moon_phase_is:blood", ctx).allowed is False
        assert registry.evaluate("tide_is:tsunami", ctx).allowed is False

        ctx.clock = None
        assert registry.evaluate("moon_phase_is:full", ctx).allowed is False
        assert registry.evaluate("tide_is:low", ctx).allowed is False

    def test_dialogue_condition_predicates(self, session: Session) -> None:
        register_conditions()
        registry = dialogue_registry()
        full_day = 4 * DAYS_PER_MOON_PHASE + 1

        ctx = self._gated_ctx(session, day=full_day, hour=HOURS_PER_TIDE)
        assert registry.evaluate({"moon_phase_is": "full"}, ctx) is True
        assert registry.evaluate({"tide_is": "high"}, ctx) is True
        assert registry.evaluate({"moon_phase_is": "new"}, ctx) is False
        assert (
            registry.evaluate({"moon_phase_is": "full", "tide_is": "low"}, ctx) is False
        )  # AND logic
