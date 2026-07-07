"""Celestial calendar: lunar phase and tide derived from the world clock.

Like ``season_for_day`` (world_clock.py), these are Tier 1 clock concerns —
pure functions of ``WorldClock`` fields with **no persisted state, no new
scheduler** (Sprint 54, engine_core.md §3.5/§3.9 read-through spirit). Tier 2
(``features/celestial``) detects transitions on the existing
``HOUR_CHANGED``/``DAY_CHANGED`` events and emits
``MOON_PHASE_CHANGED``/``TIDE_CHANGED``; content keys gates off the phase/tide
names via the condition registries or an authoritative-``Exit`` write.
"""

from __future__ import annotations

# An 8-phase, 16-day lunar month (2 days per phase) against the 30-day season:
# phases drift through the calendar rather than repeating each season, so
# moon-keyed content doesn't silently align with season-keyed content.
MOON_PHASES = (
    "new",
    "waxing_crescent",
    "first_quarter",
    "waxing_gibbous",
    "full",
    "waning_gibbous",
    "last_quarter",
    "waning_crescent",
)
DAYS_PER_MOON_PHASE = 2

# Semi-diurnal tide: two low/high cycles per 24-hour day.
# low 00:00-05:59 · high 06:00-11:59 · low 12:00-17:59 · high 18:00-23:59.
TIDES = ("low", "high")
HOURS_PER_TIDE = 6


def moon_phase_for_day(day: int) -> str:
    """The lunar phase on a given world day (days are 1-based, like seasons)."""
    phase_index = ((max(day, 1) - 1) // DAYS_PER_MOON_PHASE) % len(MOON_PHASES)
    return MOON_PHASES[phase_index]


def tide_for_hour(hour: int) -> str:
    """The tide state at a given world hour (0–23)."""
    return TIDES[(max(hour, 0) // HOURS_PER_TIDE) % len(TIDES)]
