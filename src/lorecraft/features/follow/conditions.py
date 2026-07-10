"""Escort-quest quest conditions + dialogue/quest side effects (Sprint 68).

Registers:
  - quest condition type "npc_following" (explicit npc_id — is this NPC
    currently following the player? backed by `NPC.following_player_id`,
    not `FollowService`'s in-memory player-follow graph, so no shared
    service instance is needed here)
  - quest condition type "npc_present" (explicit npc_id — is this NPC in the
    player's current room? mirrors the existing `npc_present` *command*
    condition in `engine/game/command_conditions.py`, but for quest stages)
  - dialogue/quest side effect "start_escort" (npc_id string — the NPC
    starts following the player; see `FollowService.start_escort`)
  - dialogue/quest side effect "end_escort" (npc_id string — the NPC stops
    following the player; see `FollowService.end_escort`)

Both side effects go through the shared `npc/side_effects.py` registry, the
same one quest-stage `branches[].side_effects` already use (Sprint 30.1), so
escort start/stop can be authored identically from a dialogue choice or a
quest branch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.follow.service import FollowService
from lorecraft.features.npc import side_effects
from lorecraft.features.quests import conditions as quest_conditions
from lorecraft.types import JsonObject, JsonValue

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext


def _npc_following(cond: JsonObject, ctx: "GameContext") -> bool:
    npc_id = cond.get("npc_id")
    if not isinstance(npc_id, str):
        return False
    npc = ctx.npc_repo.get(npc_id)
    return npc is not None and npc.following_player_id == ctx.player.id


def _npc_present(cond: JsonObject, ctx: "GameContext") -> bool:
    npc_id = cond.get("npc_id")
    if not isinstance(npc_id, str):
        return False
    return any(npc.id == npc_id for npc in ctx.npc_repo.in_room(ctx.room.id))


def register(follow_service: FollowService) -> None:
    """Register the escort-quest quest conditions + side effects on the shared
    Tier 1 registries. Called by the `follow` feature manifest with the same
    `FollowService` instance the event-bus cascade uses (`main.py` wires
    `services.follow.register(bus)` separately), so `start_escort`/
    `end_escort` narrate through the exact service the movement cascade reads
    escort state from. Idempotent."""

    def _handle_start_escort(data: JsonValue, ctx: "GameContext") -> None:
        follow_service.start_escort(str(data), ctx)

    def _handle_end_escort(data: JsonValue, ctx: "GameContext") -> None:
        follow_service.end_escort(str(data), ctx)

    side_effects.get_registry().register("start_escort", _handle_start_escort)
    side_effects.get_registry().register("end_escort", _handle_end_escort)
    quest_conditions.get_registry().register("npc_following", _npc_following)
    quest_conditions.get_registry().register("npc_present", _npc_present)
