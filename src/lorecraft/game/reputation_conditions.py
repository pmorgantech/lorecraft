"""Reputation-gated command/dialogue conditions (Sprint 24.3).

Registers a `reputation_at_least` command condition and a `min_reputation`
dialogue condition on the existing Tier 1 registries — no core edits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.game import command_conditions
from lorecraft.game.command_conditions import ConditionResult
from lorecraft.npc import dialogue_conditions
from lorecraft.services.reputation import ReputationService
from lorecraft.types import JsonObject

if TYPE_CHECKING:
    from lorecraft.game.context import GameContext

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


command_conditions.get_registry().register("reputation_at_least", _reputation_at_least)
dialogue_conditions.get_registry().register("min_reputation", _min_reputation_satisfied)
