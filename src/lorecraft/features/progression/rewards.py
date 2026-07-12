"""Tier 2 reward interpreter — maps the reward *vocabulary* onto Tier 1 mechanisms.

`apply_rewards` is where "which reward key means what" lives (policy). It reads a
data-driven reward payload (a quest stage's `rewards`, a discovery grant, ...) and
dispatches each recognized key to an unopinionated Tier 1 primitive:

- ``items``       → ``ItemLocationService.spawn`` (create loot on the player)
- ``coins``       → ``LedgerService.credit`` (the only sanctioned coin faucet);
  ``money`` is a tolerated alias for the same faucet
- ``xp``          → ``engine.game.leveling.award_xp`` with a curve built from the
  admin-tunable ``ProgressionConfig`` row; crossing a level triggers the derived
  level-up payout (Sprint 73.7), applied by recursively interpreting the payout
  as its own ``{coins, skill_points}`` reward payload
- any other key   → ``engine.game.leveling.apply_stat_deltas`` (e.g. ``skill_points``);
  the Tier 1 whitelist rejects a typo'd/non-numeric key loudly

The reward-key vocabulary belongs here, not in Tier 1's ``leveling`` module —
Tier 1 stays "how" (apply a delta, roll a curve), Tier 2 owns "which keys mean
what" and the balance numbers (all read from config/DB, never hardcoded).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.leveling import (
    LevelCurve,
    LevelUpResult,
    apply_stat_deltas,
    award_xp,
)
from lorecraft.features.progression.repo import ProgressionRepo
from lorecraft.types import JsonObject

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext

_ITEMS_KEY = "items"
_XP_KEY = "xp"
_COINS_KEY = "coins"
_MONEY_ALIAS = "money"  # tolerated alias for `coins`
_SKILL_POINTS_KEY = "skill_points"

# Keys the interpreter dispatches specially; every *other* key is treated as a
# numeric PlayerStats delta and validated against the Tier 1 whitelist.
_SPECIAL_KEYS = frozenset({_ITEMS_KEY, _XP_KEY, _COINS_KEY, _MONEY_ALIAS})


@dataclass(frozen=True)
class RewardOutcome:
    """What a reward grant actually did — so callers narrate without re-deriving state.

    ``coins_granted``/``stat_deltas_applied`` include any derived level-up payout
    (73.7) folded in, so the totals reflect everything the grant credited.
    ``level_up`` carries the :class:`LevelUpResult` from an ``xp`` grant (``None``
    when no xp was awarded or no progression config exists).
    """

    items_spawned: tuple[str, ...] = ()
    coins_granted: int = 0
    xp_granted: int = 0
    stat_deltas_applied: Mapping[str, int] = field(default_factory=dict)
    level_up: LevelUpResult | None = None


def _coins_amount(rewards: JsonObject) -> int:
    """Total coins requested, summing the canonical key and its tolerated alias."""
    return int(rewards.get(_COINS_KEY) or 0) + int(rewards.get(_MONEY_ALIAS) or 0)


def _carries(ctx: GameContext, item_id: str) -> bool:
    return ctx.stack_repo.quantity_of(Location("player", ctx.player.id), item_id) > 0


def _accumulate(totals: dict[str, int], deltas: Mapping[str, int]) -> None:
    for key, delta in deltas.items():
        totals[key] = totals.get(key, 0) + delta


def apply_rewards(ctx: GameContext, rewards: JsonObject) -> RewardOutcome:
    """Interpret a data-driven ``rewards`` payload, dispatching each key to Tier 1.

    Order is fixed (items, coins, xp+level-up, remaining stat deltas) so a bundle
    granting several kinds at once applies deterministically. Grants are additive:
    an explicit ``skill_points`` reward and a level-up's skill-point payout both
    apply. Returns a :class:`RewardOutcome` summarizing what was actually granted.
    """
    player_id = ctx.player.id
    items_spawned: list[str] = []
    coins_granted = 0
    xp_granted = 0
    stat_deltas_applied: dict[str, int] = {}
    level_up: LevelUpResult | None = None

    # items -> Tier 1 spawn. Preserve the prior quest behavior: skip an unknown
    # item id or one the player already carries rather than erroring.
    for raw_id in rewards.get(_ITEMS_KEY) or []:
        item_id = str(raw_id)
        if ctx.item_repo.get(item_id) is None or _carries(ctx, item_id):
            continue
        ctx.item_location.spawn(item_id, Location("player", player_id))
        items_spawned.append(item_id)

    # coins -> Tier 1 ledger.credit (the only sanctioned way coins enter play).
    coins = _coins_amount(rewards)
    if coins > 0:
        ctx.ledger.credit(ctx.session, "player", player_id, coins)
        coins_granted += coins

    # xp -> Tier 1 leveling with a config-built curve; a level-up recursively
    # interprets its own derived payout (73.7). A player with no PlayerStats row
    # can't hold xp, and a world with no ProgressionConfig has no curve — in the
    # latter case xp is banked without progression, mirroring pre-Sprint-73
    # behavior so an unconfigured world's rewards/discovery don't break.
    xp_amount = int(rewards.get(_XP_KEY) or 0)
    if xp_amount > 0:
        stats = ctx.player_repo.stats(player_id)
        if stats is not None:
            config = ProgressionRepo(ctx.session).config()
            if config is None:
                stats.xp += xp_amount
                xp_granted += xp_amount
            else:
                level_up = award_xp(
                    stats, xp_amount, LevelCurve(base=config.base, step=config.step)
                )
                xp_granted += xp_amount
                if level_up.levels_gained > 0:
                    payout: JsonObject = {
                        _COINS_KEY: config.coins_per_level * level_up.levels_gained,
                        _SKILL_POINTS_KEY: (
                            config.skill_points_per_level * level_up.levels_gained
                        ),
                    }
                    sub = apply_rewards(ctx, payout)
                    coins_granted += sub.coins_granted
                    _accumulate(stat_deltas_applied, sub.stat_deltas_applied)

    # any remaining key -> numeric PlayerStats delta (Tier 1 whitelist validates).
    deltas = {k: int(v) for k, v in rewards.items() if k not in _SPECIAL_KEYS}
    if deltas:
        stats = ctx.player_repo.stats(player_id)
        if stats is not None:
            apply_stat_deltas(stats, deltas)
            _accumulate(stat_deltas_applied, deltas)

    return RewardOutcome(
        items_spawned=tuple(items_spawned),
        coins_granted=coins_granted,
        xp_granted=xp_granted,
        stat_deltas_applied=stat_deltas_applied,
        level_up=level_up,
    )
