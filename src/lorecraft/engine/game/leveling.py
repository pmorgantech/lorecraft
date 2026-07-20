"""Generic XP/leveling *mechanism* — pure, data-driven, opinion-free (Tier 1).

Like `engine/game/checks.py::skill_check`, this module knows *how* a class of
thing works but never *what* it should be for any particular feature. It can add
XP, roll a player across one or more level thresholds described by a caller-
supplied :class:`LevelCurve`, and apply an arbitrary integer delta to a
whitelist of numeric `PlayerStats` fields. It has **no concept** of coins, skill
trees, or "what a level grants" — that policy lives in Tier 2
(`features/progression/`), which builds the curve from admin-tunable config and
decides the reward payload. No session, no IO, no `GameContext`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lorecraft.engine.models.player import PlayerStats
from lorecraft.errors import ValidationError

# The numeric `PlayerStats` columns that `apply_stat_deltas` may mutate. A
# whitelist (not `hasattr`) so a typo'd or non-numeric key (`skills`, `traits`,
# `player_id`) is rejected loudly rather than silently corrupting state. Tier 2
# reward policy targets these keys with data-driven deltas.
_MUTABLE_STAT_FIELDS: frozenset[str] = frozenset(
    {
        "strength",
        "agility",
        "vitality",
        "intellect",
        "presence",
        "fortitude",
        "max_hp",
        "level",
        "xp",
        "xp_to_next",
        "skill_points",
    }
)


@dataclass(frozen=True)
class LevelCurve:
    """Threshold *data* describing how much XP each level costs.

    Two mutually compatible modes, both supplied by the caller from config (never
    a hardcoded module constant):

    - **Formula:** ``base`` + ``step`` — the cost to advance *from* level ``n`` is
      ``base + step * (n - 1)`` (so ``base`` is the level 1→2 cost).
    - **Explicit:** an optional ``thresholds`` tuple of incremental costs indexed
      by ``level - 1`` (``thresholds[0]`` is the 1→2 cost). Levels beyond the last
      listed threshold fall back to repeating the final entry, so an explicit
      curve is never undefined for high levels.
    """

    base: int = 0
    step: int = 0
    thresholds: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.thresholds:
            if any(cost <= 0 for cost in self.thresholds):
                raise ValidationError(
                    "LevelCurve thresholds must all be positive",
                    code="validation_level_curve",
                )
        else:
            if self.base <= 0:
                raise ValidationError(
                    "LevelCurve base must be positive when no thresholds are given",
                    code="validation_level_curve",
                )
            if self.step < 0:
                raise ValidationError(
                    "LevelCurve step must be non-negative",
                    code="validation_level_curve",
                )


@dataclass(frozen=True)
class LevelUpResult:
    """Outcome of an :func:`award_xp` call."""

    leveled_up: bool
    old_level: int
    new_level: int
    levels_gained: int


def xp_for_level(curve: LevelCurve, level: int) -> int:
    """XP required to advance *from* ``level`` to ``level + 1`` under ``curve``."""
    if level < 1:
        raise ValidationError(
            f"level must be >= 1, got {level}", code="validation_level"
        )
    if curve.thresholds:
        index = min(level - 1, len(curve.thresholds) - 1)
        return curve.thresholds[index]
    return curve.base + curve.step * (level - 1)


def award_xp(stats: PlayerStats, amount: int, curve: LevelCurve) -> LevelUpResult:
    """Add ``amount`` XP and roll ``stats`` across every threshold it crosses.

    ``stats.xp`` is progress *within* the current level; each level-up subtracts
    that level's cost and carries the remainder forward, so a single large award
    can cross multiple levels. ``stats.xp_to_next`` is refreshed to the (possibly
    new) current level's cost. Grants nothing but XP and levels — the caller
    decides any coin/skill-point reward from ``levels_gained``.
    """
    if amount < 0:
        raise ValidationError(
            f"XP amount must be non-negative, got {amount}", code="validation_xp"
        )
    old_level = stats.level
    stats.xp += amount
    levels_gained = 0
    while stats.xp >= xp_for_level(curve, stats.level):
        stats.xp -= xp_for_level(curve, stats.level)
        stats.level += 1
        levels_gained += 1
    stats.xp_to_next = xp_for_level(curve, stats.level)
    return LevelUpResult(
        leveled_up=levels_gained > 0,
        old_level=old_level,
        new_level=stats.level,
        levels_gained=levels_gained,
    )


# Fields where "below this value" is never a valid state, regardless of what
# Tier 2 reward/penalty policy asked for — a Tier 1 invariant, not a game-
# design opinion (a player record can't be level 0, or owe negative XP/skill
# points). Every other mutable field (strength, agility, ..., max_hp,
# xp_to_next) is caller-owned: Tier 1 applies the delta as given with no
# floor, since what's valid there (e.g. can max_hp ever be reduced below 1?)
# is a Tier 2 policy decision.
_FLOORED_STAT_FIELDS: Mapping[str, int] = {
    "level": 1,
    "skill_points": 0,
    "xp": 0,
}


def apply_stat_deltas(stats: PlayerStats, deltas: Mapping[str, int]) -> None:
    """Apply integer deltas to whitelisted numeric ``PlayerStats`` fields.

    The generic "update an array of player properties" primitive: Tier 2 reward
    policy names the fields and amounts; this mechanism only enforces that each
    key is a known numeric field and applies the delta. Unknown keys raise rather
    than being silently dropped.

    A delta that would push ``level``/``skill_points``/``xp`` below their floor
    (see ``_FLOORED_STAT_FIELDS``) is clamped at the floor rather than going
    negative or to zero-level; it does not raise, since a Tier 2 penalty that
    overshoots a floor (e.g. "lose 5 skill points" when the player has 2) is a
    normal, expected case, not a bug. Every other whitelisted field is
    caller-owned and applied unclamped.
    """
    for key in deltas:
        if key not in _MUTABLE_STAT_FIELDS:
            raise ValidationError(
                f"Unknown player stat field: {key!r}",
                code="validation_unknown_stat",
            )
    for key, delta in deltas.items():
        new_value = getattr(stats, key) + delta
        floor = _FLOORED_STAT_FIELDS.get(key)
        if floor is not None and new_value < floor:
            new_value = floor
        setattr(stats, key, new_value)
