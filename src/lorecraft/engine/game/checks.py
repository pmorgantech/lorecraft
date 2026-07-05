"""Skill-check resolution — one roll-under-d100 helper for every check.

See docs/engine_core.md §3.6. Identical resolution for perception, lockpicking,
bartering, and combat-to-hit; skill *identity* (which skills exist, use-based
improvement) is Tier 2 (Sprint 24). This module only defines *how a check
resolves*, over the seedable GameRng (§3.6) and the modifier resolver (§3.5).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from lorecraft.engine.game.modifiers import Modifier, resolve
from lorecraft.engine.game.rng import GameRng

# There is ALWAYS at least a 5% chance either way — no impossible checks, no
# sure things. Engine constants; a world wanting different bounds overrides
# via Tier 2 config later.
CHECK_FLOOR = 5
CHECK_CEIL = 95


@dataclass(frozen=True)
class CheckResult:
    success: bool
    roll: int  # the raw d100
    effective: float  # resolved skill after modifiers
    target: int  # clamped success threshold actually used
    margin: int  # target - roll (positive = comfortable success)


def skill_check(
    rng: GameRng,
    *,
    base: float,
    difficulty: int,
    modifiers: Iterable[Modifier] = (),
    key: str = "check",
) -> CheckResult:
    """Roll-under d100 skill check.

    effective = resolve(key, base, modifiers); target = clamp(round(effective)
    - difficulty, CHECK_FLOOR, CHECK_CEIL); success = rng.randint(1, 100) <=
    target. difficulty 0 = routine; positive = harder.
    """
    effective = resolve(key, base, modifiers)
    target = max(CHECK_FLOOR, min(CHECK_CEIL, round(effective) - difficulty))
    roll = rng.randint(1, 100)
    return CheckResult(
        success=roll <= target,
        roll=roll,
        effective=effective,
        target=target,
        margin=target - roll,
    )
