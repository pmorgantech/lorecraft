"""Data-driven ability *usage* gating (Sprint 78.8).

Bridges a live `GameContext` to the opinion-free Tier 1 `check_usage` mechanism
(§2, §5.3): it assembles the actor/world snapshots `check_usage` needs from the
player's flags and the current room, then evaluates an ability's data-authored
`usage:` block. This replaces per-verb hardcoded Python gating (e.g. forage's
`Room.indoor == False`) with a generic, content-authored check — the verb keeps
only its narration + effect, not its gatekeeping.

Assembly is intentionally minimal for the v1 ability set: durable `state.<name>`
requirements resolve against `Player.flags`, and terrain against the room. No v1
ability declares a transient-effect state, a stamina cost, or a cooldown, so held
`ActiveEffect`s / resource meters / per-player cooldown stores are not wired in
here yet — an ability that authors those fields would extend this assembly (the
Tier 1 mechanism already handles them).
"""

from __future__ import annotations

from lorecraft.engine.game.abilities import (
    ActorState,
    UsageResult,
    WorldState,
    check_usage,
)
from lorecraft.engine.game.context import GameContext
from lorecraft.features.disciplines.abilities import (
    AbilityRegistry,
    get_ability_registry,
)


def _actor_state(ctx: GameContext) -> ActorState:
    """Snapshot the acting player's usage-relevant state (durable flags only)."""
    flags = frozenset(key for key, value in ctx.player.flags.items() if value)
    return ActorState(flags=flags)


def _world_state(ctx: GameContext) -> WorldState:
    """Snapshot ambient terrain from the current room.

    The room's terrain tag plus a derived `outdoor`/`indoor` tag form the terrain
    set an ability's `usage.terrain` matches against — this is what lets forage's
    `terrain: [outdoor]` replace its old `Room.indoor == False` Python check.
    `now_epoch` is 0.0: no v1 ability has a cooldown, and `is_off_cooldown`
    ignores it when no cooldown is recorded.
    """
    room = ctx.room
    terrain: set[str] = set()
    if room.terrain:
        terrain.add(room.terrain)
    terrain.add("indoor" if room.indoor else "outdoor")
    return WorldState(now_epoch=0.0, terrain=frozenset(terrain))


def evaluate_usage(
    ctx: GameContext,
    ability_id: str,
    *,
    registry: AbilityRegistry | None = None,
    target: ActorState | None = None,
) -> UsageResult | None:
    """Evaluate ``ability_id``'s data-driven `usage:` block against ``ctx``.

    Returns the Tier 1 `UsageResult` (whose per-requirement booleans let the verb
    narrate the specific block), or ``None`` when the ability has no record loaded
    — in which case the caller imposes no data-driven usage gate.
    """
    reg = registry or get_ability_registry()
    record = reg.get(ability_id)
    if record is None:
        return None
    return check_usage(
        _actor_state(ctx), record.to_ability_def(), target, _world_state(ctx)
    )
