"""Celestial transitions: emit moon/tide change events off the clock (Sprint 54).

The weather-handler pattern: subscribe to the runner's existing
``DAY_CHANGED``/``HOUR_CHANGED`` events and emit
``MOON_PHASE_CHANGED``/``TIDE_CHANGED`` when the derived state differs between
the event's endpoints. Pure derivation (engine/clock/celestial.py) — no
session, no commit, no new scheduler. A fast-forward that passes *through*
intermediate states compares endpoints only, which is the game-meaningful
answer ("did the tide turn?"), not a replay of every skipped hour.
"""

from __future__ import annotations

from lorecraft.engine.clock.celestial import moon_phase_for_day, tide_for_hour
from lorecraft.engine.game.events import Event, EventBus, GameEvent


def _as_int(value: object) -> int:
    """Coerce a JsonValue payload field to int (0 for absent/non-numeric)."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def register_celestial_handlers(bus: EventBus) -> None:
    def on_day_changed(event: Event, ctx: object) -> None:
        previous_day = _as_int(event.payload.get("previous_day"))
        day = _as_int(event.payload.get("day"))
        previous_phase = moon_phase_for_day(previous_day)
        phase = moon_phase_for_day(day)
        if phase == previous_phase:
            return
        bus.emit(
            Event(
                GameEvent.MOON_PHASE_CHANGED,
                {"previous_phase": previous_phase, "phase": phase, "day": day},
            ),
            ctx,
        )

    def on_hour_changed(event: Event, ctx: object) -> None:
        previous_hour = _as_int(event.payload.get("previous_hour"))
        hour = _as_int(event.payload.get("hour"))
        previous_tide = tide_for_hour(previous_hour)
        tide = tide_for_hour(hour)
        if tide == previous_tide:
            return
        bus.emit(
            Event(
                GameEvent.TIDE_CHANGED,
                {"previous_tide": previous_tide, "tide": tide, "hour": hour},
            ),
            ctx,
        )

    bus.on(GameEvent.DAY_CHANGED, on_day_changed)
    bus.on(GameEvent.HOUR_CHANGED, on_hour_changed)
