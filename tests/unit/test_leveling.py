"""Unit tests for the Tier 1 generic leveling mechanism (engine/game/leveling.py)."""

from __future__ import annotations

import pytest

from lorecraft.engine.game.leveling import (
    LevelCurve,
    apply_stat_deltas,
    award_xp,
    xp_for_level,
)
from lorecraft.engine.models.player import PlayerStats
from lorecraft.errors import ValidationError


def _stats(**overrides: int) -> PlayerStats:
    stats = PlayerStats(player_id="p1")
    for key, value in overrides.items():
        setattr(stats, key, value)
    return stats


# --- LevelCurve / xp_for_level ------------------------------------------------


def test_xp_for_level_formula_uses_base_and_step() -> None:
    curve = LevelCurve(base=100, step=50)
    assert xp_for_level(curve, 1) == 100
    assert xp_for_level(curve, 2) == 150
    assert xp_for_level(curve, 3) == 200


def test_xp_for_level_flat_curve_when_step_zero() -> None:
    curve = LevelCurve(base=100, step=0)
    assert xp_for_level(curve, 1) == 100
    assert xp_for_level(curve, 5) == 100


def test_explicit_thresholds_indexed_by_level() -> None:
    curve = LevelCurve(thresholds=(100, 200, 400))
    assert xp_for_level(curve, 1) == 100
    assert xp_for_level(curve, 2) == 200
    assert xp_for_level(curve, 3) == 400


def test_explicit_thresholds_repeat_last_beyond_list() -> None:
    curve = LevelCurve(thresholds=(100, 200))
    assert xp_for_level(curve, 3) == 200
    assert xp_for_level(curve, 99) == 200


def test_curve_driven_entirely_by_passed_data() -> None:
    # No module-level default: two different caller-supplied curves give
    # different costs for the same level.
    assert xp_for_level(LevelCurve(base=10, step=0), 1) == 10
    assert xp_for_level(LevelCurve(base=999, step=0), 1) == 999


def test_curve_rejects_nonpositive_base() -> None:
    with pytest.raises(ValidationError):
        LevelCurve(base=0, step=10)


def test_curve_rejects_negative_step() -> None:
    with pytest.raises(ValidationError):
        LevelCurve(base=100, step=-1)


def test_curve_rejects_nonpositive_threshold() -> None:
    with pytest.raises(ValidationError):
        LevelCurve(thresholds=(100, 0, 200))


def test_xp_for_level_rejects_level_below_one() -> None:
    with pytest.raises(ValidationError):
        xp_for_level(LevelCurve(base=100), 0)


# --- award_xp -----------------------------------------------------------------


def test_award_xp_no_level_up_below_threshold() -> None:
    stats = _stats()  # level 1, xp 0
    curve = LevelCurve(base=100, step=50)
    result = award_xp(stats, 40, curve)
    assert result.leveled_up is False
    assert result.levels_gained == 0
    assert result.old_level == 1 and result.new_level == 1
    assert stats.xp == 40
    assert stats.xp_to_next == 100


def test_award_xp_single_level_rollover_carries_remainder() -> None:
    stats = _stats()
    curve = LevelCurve(base=100, step=50)
    result = award_xp(stats, 130, curve)
    assert result.leveled_up is True
    assert result.levels_gained == 1
    assert result.old_level == 1 and result.new_level == 2
    assert stats.level == 2
    assert stats.xp == 30  # 130 - 100
    assert stats.xp_to_next == 150  # cost of level 2 -> 3


def test_award_xp_multi_level_rollover_in_one_call() -> None:
    stats = _stats()
    curve = LevelCurve(base=100, step=50)  # costs: 100, 150, 200, ...
    result = award_xp(stats, 300, curve)
    # 300 -> lvl2 (xp 200), -> lvl3 (xp 50); 50 < 200 stop.
    assert result.levels_gained == 2
    assert result.new_level == 3
    assert stats.level == 3
    assert stats.xp == 50
    assert stats.xp_to_next == 200


def test_award_xp_exact_threshold_boundary_levels_up() -> None:
    stats = _stats()
    curve = LevelCurve(base=100, step=0)
    result = award_xp(stats, 100, curve)
    assert result.levels_gained == 1
    assert stats.level == 2
    assert stats.xp == 0
    assert stats.xp_to_next == 100


def test_award_xp_zero_amount_is_noop() -> None:
    stats = _stats(xp=25)
    curve = LevelCurve(base=100, step=50)
    result = award_xp(stats, 0, curve)
    assert result.leveled_up is False
    assert stats.xp == 25
    assert stats.level == 1


def test_award_xp_negative_amount_rejected() -> None:
    stats = _stats()
    with pytest.raises(ValidationError):
        award_xp(stats, -5, LevelCurve(base=100))


# --- apply_stat_deltas --------------------------------------------------------


def test_apply_stat_deltas_updates_whitelisted_fields() -> None:
    stats = _stats(xp=10, strength=10)
    apply_stat_deltas(stats, {"xp": 5, "strength": 3})
    assert stats.xp == 15
    assert stats.strength == 13


def test_apply_stat_deltas_updates_skill_points() -> None:
    stats = _stats(skill_points=1)
    apply_stat_deltas(stats, {"skill_points": 2})
    assert stats.skill_points == 3


def test_apply_stat_deltas_rejects_unknown_property() -> None:
    stats = _stats()
    with pytest.raises(ValidationError):
        apply_stat_deltas(stats, {"coins": 100})


def test_apply_stat_deltas_rejects_before_partial_mutation() -> None:
    # A rejected key must not leave earlier keys half-applied.
    stats = _stats(xp=10)
    with pytest.raises(ValidationError):
        apply_stat_deltas(stats, {"xp": 5, "bogus": 1})
    assert stats.xp == 10


def test_apply_stat_deltas_rejects_non_numeric_field() -> None:
    stats = _stats()
    with pytest.raises(ValidationError):
        apply_stat_deltas(stats, {"skills": 1})
