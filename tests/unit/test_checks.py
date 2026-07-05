"""Unit tests for skill_check (engine_core.md §3.6)."""

from __future__ import annotations

from lorecraft.engine.game.checks import CHECK_CEIL, CHECK_FLOOR, skill_check
from lorecraft.engine.game.modifiers import Modifier
from lorecraft.engine.game.rng import GameRng


def test_routine_check_uses_effective_skill_as_target() -> None:
    rng = GameRng(1)
    result = skill_check(rng, base=50.0, difficulty=0)
    assert result.effective == 50.0
    assert result.target == 50


def test_positive_difficulty_lowers_target() -> None:
    rng = GameRng(1)
    result = skill_check(rng, base=50.0, difficulty=20)
    assert result.target == 30


def test_negative_difficulty_raises_target() -> None:
    rng = GameRng(1)
    result = skill_check(rng, base=50.0, difficulty=-10)
    assert result.target == 60


def test_target_never_below_floor() -> None:
    rng = GameRng(1)
    result = skill_check(rng, base=10.0, difficulty=90)
    assert result.target == CHECK_FLOOR


def test_target_never_above_ceiling() -> None:
    rng = GameRng(1)
    result = skill_check(rng, base=200.0, difficulty=-50)
    assert result.target == CHECK_CEIL


def test_modifiers_feed_into_effective_and_target() -> None:
    rng = GameRng(1)
    modifiers = [Modifier("perception", "add", 10.0, "item:helm")]
    result = skill_check(
        rng, base=30.0, difficulty=0, modifiers=modifiers, key="perception"
    )
    assert result.effective == 40.0
    assert result.target == 40


def test_success_iff_roll_within_target() -> None:
    rng = GameRng(1)
    result = skill_check(rng, base=50.0, difficulty=0)
    assert result.success == (result.roll <= result.target)
    assert result.margin == result.target - result.roll


def test_same_seed_produces_identical_check_result() -> None:
    a = skill_check(GameRng(123), base=50.0, difficulty=10)
    b = skill_check(GameRng(123), base=50.0, difficulty=10)
    assert a == b


def test_margin_positive_on_comfortable_success() -> None:
    # Force a guaranteed success: target=95 (ceiling), roll must be <= 95,
    # which is true unless the die lands exactly 96-100 (5% chance). Run many
    # seeds and just confirm the success/margin relationship holds each time.
    for seed in range(50):
        result = skill_check(GameRng(seed), base=200.0, difficulty=-50)
        assert result.target == CHECK_CEIL
        assert result.success == (result.roll <= CHECK_CEIL)
        if result.success:
            assert result.margin >= 0
        else:
            assert result.margin < 0
