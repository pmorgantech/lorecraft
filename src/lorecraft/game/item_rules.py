"""Bound-item policy rule (docs/inventory_equipment.md §4).

`Item.bound` items can't be dropped or given away — a RuleEngine rule
checked at the command layer, not inside ItemLocationService.move()
(engine_core.md §2's "security/integrity veto -> a rule" line: this is
policy, not a mechanical invariant, so it belongs here, fail-closed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.engine.game.rules import RuleEngine, RuleFn, RuleResult
from lorecraft.types import JsonObject

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext


def _bound_item_veto(ctx: object, payload: JsonObject) -> RuleResult:
    # ctx.parsed_command isn't set yet at rule-check time (game/engine.py sets
    # it after rules.check() returns) — the noun the command engine already
    # extracted into the audit payload is the only reliable source here.
    game_ctx: "GameContext" = ctx  # type: ignore[assignment]
    noun = payload.get("noun")
    if not isinstance(noun, str):
        return RuleResult.allow()

    matches = game_ctx.item_repo.search_player_items(game_ctx.player.id, noun)
    for item in matches:
        if item.bound:
            return RuleResult.block(
                f"The {item.name} is bound to you and can't be let go."
            )
    return RuleResult.allow()


def register_item_rules(rules: RuleEngine) -> None:
    veto: RuleFn = _bound_item_veto
    rules.register_rule("drop", veto)
    rules.register_rule("give", veto)
