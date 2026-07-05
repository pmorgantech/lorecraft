"""Reputation-gated command/dialogue conditions (Sprint 24.3).

Registers a `reputation_at_least` command condition and a `min_reputation`
dialogue condition on the existing Tier 1 registries — no core edits.

Sprint 30.1 adds the flip side: an `adjust_reputation` side effect on the
shared npc/side_effects.py registry, so dialogue choices and quest
branches can make standing changes a *consequence* ("world-state/standing
changes" per docs/roadmap.md Sprint 30.1), not just a gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.engine.game import command_conditions
from lorecraft.engine.game.command_conditions import ConditionResult
from lorecraft.features.npc import dialogue_conditions, side_effects
from lorecraft.features.reputation.service import ReputationService
from lorecraft.types import JsonObject, JsonValue

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext

_reputation = ReputationService()


def _reputation_at_least(parameter: str, ctx: "GameContext") -> ConditionResult:
    parts = parameter.split(":", 2)
    if len(parts) != 3:
        return ConditionResult(True)
    target_type, target_id, min_standing_raw = parts
    try:
        min_standing = int(min_standing_raw)
    except ValueError:
        return ConditionResult(True)

    standing = _reputation.standing_of(
        ctx.session, ctx.player.id, target_type, target_id
    )
    if standing < min_standing:
        return ConditionResult(False, "They don't trust you enough for that yet.")
    return ConditionResult(True)


def _min_reputation_satisfied(data: JsonObject, ctx: "GameContext") -> bool:
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    min_standing = data.get("min")
    if not isinstance(target_type, str) or not isinstance(target_id, str):
        return True
    if not isinstance(min_standing, (int, float)):
        return True
    standing = _reputation.standing_of(
        ctx.session, ctx.player.id, target_type, target_id
    )
    return standing >= min_standing


def _handle_adjust_reputation(data: JsonValue, ctx: "GameContext") -> None:
    """`adjust_reputation: {target_type: npc, target_id: thor, delta: 10}`."""
    if not isinstance(data, dict):
        return
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    delta = data.get("delta")
    if not isinstance(target_type, str) or not isinstance(target_id, str):
        return
    if not isinstance(delta, (int, float)) or isinstance(delta, bool):
        return
    _reputation.adjust(ctx.session, ctx.player.id, target_type, target_id, int(delta))


def register() -> None:
    """Register the reputation conditions + `adjust_reputation` side effect on
    the shared Tier 1 registries.

    Called by the `reputation` feature's manifest (`lorecraft/features/
    reputation`) when the feature is enabled — no longer a module-level import
    side effect, so disabling the feature actually leaves these unregistered.
    Idempotent: re-registering the same names simply overwrites.
    """
    command_conditions.get_registry().register(
        "reputation_at_least", _reputation_at_least
    )
    dialogue_conditions.get_registry().register(
        "min_reputation", _min_reputation_satisfied
    )
    side_effects.get_registry().register("adjust_reputation", _handle_adjust_reputation)
