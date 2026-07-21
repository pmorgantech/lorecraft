"""Sprint 54.1: celestial calendar — moon phase + tide as pure clock functions."""

from __future__ import annotations

from lorecraft.engine.clock.celestial import (
    DAY_PHASES,
    DAYS_PER_MOON_PHASE,
    HOURS_PER_TIDE,
    MOON_PHASES,
    TIDES,
    day_phase_for_hour,
    moon_phase_for_day,
    tide_for_hour,
)


class TestMoonPhase:
    def test_month_starts_new(self) -> None:
        assert moon_phase_for_day(1) == "new"
        assert moon_phase_for_day(DAYS_PER_MOON_PHASE) == "new"

    def test_phase_advances_every_period(self) -> None:
        assert moon_phase_for_day(DAYS_PER_MOON_PHASE + 1) == "waxing_crescent"
        # Middle of the cycle: day 9-10 of a 16-day month is full.
        full_start = 4 * DAYS_PER_MOON_PHASE + 1
        assert moon_phase_for_day(full_start) == "full"

    def test_cycle_wraps(self) -> None:
        month = len(MOON_PHASES) * DAYS_PER_MOON_PHASE
        assert moon_phase_for_day(month) == "waning_crescent"
        assert moon_phase_for_day(month + 1) == "new"
        assert moon_phase_for_day(3 * month + 5) == moon_phase_for_day(5)

    def test_degenerate_days_clamp_to_first(self) -> None:
        assert moon_phase_for_day(0) == "new"
        assert moon_phase_for_day(-3) == "new"

    def test_every_phase_reachable(self) -> None:
        month = len(MOON_PHASES) * DAYS_PER_MOON_PHASE
        seen = {moon_phase_for_day(day) for day in range(1, month + 1)}
        assert seen == set(MOON_PHASES)


class TestTide:
    def test_semi_diurnal_cycle(self) -> None:
        assert tide_for_hour(0) == "low"
        assert tide_for_hour(HOURS_PER_TIDE - 1) == "low"
        assert tide_for_hour(HOURS_PER_TIDE) == "high"
        assert tide_for_hour(2 * HOURS_PER_TIDE) == "low"
        assert tide_for_hour(3 * HOURS_PER_TIDE) == "high"
        assert tide_for_hour(23) == "high"

    def test_two_full_cycles_per_day(self) -> None:
        changes = sum(
            1 for hour in range(1, 24) if tide_for_hour(hour) != tide_for_hour(hour - 1)
        )
        assert changes == 3  # low→high→low→high across one day

    def test_degenerate_hours_clamp(self) -> None:
        assert tide_for_hour(-1) == "low"

    def test_states_are_the_declared_ones(self) -> None:
        assert {tide_for_hour(h) for h in range(24)} == set(TIDES)


class TestDayPhase:
    def test_boundaries(self) -> None:
        # dawn 05:00-07:59
        assert day_phase_for_hour(4) == "night"
        assert day_phase_for_hour(5) == "dawn"
        assert day_phase_for_hour(7) == "dawn"
        # day 08:00-17:59
        assert day_phase_for_hour(8) == "day"
        assert day_phase_for_hour(17) == "day"
        # dusk 18:00-20:59
        assert day_phase_for_hour(18) == "dusk"
        assert day_phase_for_hour(20) == "dusk"
        # night 21:00-04:59
        assert day_phase_for_hour(21) == "night"
        assert day_phase_for_hour(23) == "night"
        assert day_phase_for_hour(0) == "night"

    def test_night_wraps_past_midnight(self) -> None:
        # 21:00 through 04:59 is one contiguous night, not two buckets.
        assert all(
            day_phase_for_hour(h) == "night" for h in (21, 22, 23, 0, 1, 2, 3, 4)
        )

    def test_out_of_range_hours_normalize(self) -> None:
        assert day_phase_for_hour(24) == day_phase_for_hour(0)
        assert day_phase_for_hour(29) == day_phase_for_hour(5)
        assert day_phase_for_hour(-1) == "night"  # clamped to 0 → night

    def test_every_phase_reachable(self) -> None:
        assert {day_phase_for_hour(h) for h in range(24)} == set(DAY_PHASES)
