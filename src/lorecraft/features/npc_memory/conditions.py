"""NPC memory dialogue condition/side-effect + quest condition (Sprint 30.1).

NPC memory is per-(player, npc): dialogue authors write a generic key like
"helped" in any NPC's tree, and it is automatically scoped to whichever NPC
the player is currently talking to -- no need to pre-name one flag per NPC
pair (e.g. "helped_thor", "helped_mira", ...) the way Player.flags would
require.

Registers:
  - dialogue condition "npc_remembers" (list of keys, all must be remembered
    for the current dialogue NPC)
  - dialogue side effect "remember" (list of keys -> set True, or a
    key->value dict for explicit values)
  - quest condition type "npc_remembers" (explicit npc_id + flag/key, since
    quest conditions are not evaluated inside an active dialogue)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.quests import conditions as quest_conditions
from lorecraft.npc import dialogue_conditions, side_effects
from lorecraft.features.npc_memory.repo import NpcMemoryRepo
from lorecraft.types import JsonObject, JsonScalar, JsonValue

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext


def _npc_remembers_satisfied(data: JsonValue, ctx: "GameContext") -> bool:
    from lorecraft.npc.dialogue import current_npc_id

    npc_id = current_npc_id(ctx)
    if npc_id is None or not isinstance(data, list):
        return False
    repo = NpcMemoryRepo(ctx.session)
    return all(repo.remembers(ctx.player.id, npc_id, str(key)) for key in data)


def _as_scalar(value: JsonValue) -> JsonScalar:
    return value if not isinstance(value, (list, dict)) else True


def _handle_remember(data: JsonValue, ctx: "GameContext") -> None:
    from lorecraft.npc.dialogue import current_npc_id

    npc_id = current_npc_id(ctx)
    if npc_id is None:
        return
    repo = NpcMemoryRepo(ctx.session)
    if isinstance(data, dict):
        for key, value in data.items():
            repo.set(ctx.player.id, npc_id, str(key), _as_scalar(value))
    elif isinstance(data, list):
        for key in data:
            repo.set(ctx.player.id, npc_id, str(key), True)


def _quest_npc_remembers(cond: JsonObject, ctx: "GameContext") -> bool:
    npc_id = cond.get("npc_id")
    key = cond.get("flag")
    if not isinstance(npc_id, str) or not isinstance(key, str):
        return False
    return NpcMemoryRepo(ctx.session).remembers(ctx.player.id, npc_id, key)


def register() -> None:
    """Register the NPC-memory dialogue condition/side effect + quest condition
    on the shared Tier 1 registries. Called by the `npc_memory` feature manifest
    when enabled (no longer a module-level import side effect). Idempotent."""
    dialogue_conditions.get_registry().register(
        "npc_remembers", _npc_remembers_satisfied
    )
    side_effects.get_registry().register("remember", _handle_remember)
    quest_conditions.get_registry().register("npc_remembers", _quest_npc_remembers)
