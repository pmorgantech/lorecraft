"""Skill-tree purchase service (Sprint 74.3) — the skill-point *sink*.

Spends `PlayerStats.skill_points` on a node, performing the mandatory dual-write:
record the node in `unlocked_nodes` (query/UI) *and* set every `ability.<id>`
flag on `Player.flags` (the load-bearing gate active verbs / dialogue read).
Passive `modifier` blocks need no wiring here — the modifier source (74.4) reads
`unlocked_nodes` live, so a purchase applies retroactively with zero extra state.

Stateless per call, mutating the caller's session objects without committing —
the same session discipline every other Tier 2 service follows.
"""

from __future__ import annotations

from dataclasses import dataclass

from lorecraft.engine.game.context import GameContext
from lorecraft.features.progression.skill_tree import (
    SkillTreeNode,
    SkillTreeRegistry,
    get_registry,
)


@dataclass(frozen=True)
class PurchaseResult:
    """Outcome of a purchase attempt, with a player-facing reason on failure."""

    ok: bool
    reason: str
    node: SkillTreeNode | None = None


class SkillTreeService:
    def __init__(self, registry: SkillTreeRegistry | None = None) -> None:
        self._registry = registry or get_registry()

    def _unlocked(self, ctx: GameContext) -> set[str]:
        stats = ctx.player_repo.stats(ctx.player.id)
        return set(stats.unlocked_nodes) if stats is not None else set()

    def _prereqs_met(self, node: SkillTreeNode, unlocked: set[str]) -> bool:
        return all(prereq in unlocked for prereq in node.prerequisites)

    def owned_nodes(self, ctx: GameContext) -> list[SkillTreeNode]:
        unlocked = self._unlocked(ctx)
        return [n for n in self._registry.all() if n.id in unlocked]

    def available_nodes(self, ctx: GameContext) -> list[SkillTreeNode]:
        """Not-yet-owned nodes whose prerequisites are met and cost is affordable."""
        stats = ctx.player_repo.stats(ctx.player.id)
        points = stats.skill_points if stats is not None else 0
        unlocked = self._unlocked(ctx)
        return [
            n
            for n in self._registry.all()
            if n.id not in unlocked
            and self._prereqs_met(n, unlocked)
            and n.cost <= points
        ]

    def locked_nodes(self, ctx: GameContext) -> list[SkillTreeNode]:
        """Not-yet-owned nodes blocked by unmet prerequisites or cost."""
        stats = ctx.player_repo.stats(ctx.player.id)
        points = stats.skill_points if stats is not None else 0
        unlocked = self._unlocked(ctx)
        return [
            n
            for n in self._registry.all()
            if n.id not in unlocked
            and (not self._prereqs_met(n, unlocked) or n.cost > points)
        ]

    def purchase(self, ctx: GameContext, node_id: str) -> PurchaseResult:
        """Attempt to buy `node_id`. Never silently no-ops — every failure path
        returns a distinct reason. On success mutates stats + flags in place."""
        node = self._registry.get(node_id)
        if node is None:
            return PurchaseResult(False, f"There is no ability called '{node_id}'.")

        stats = ctx.player_repo.stats(ctx.player.id)
        if stats is None:
            return PurchaseResult(False, "You have no skill points to spend.", node)

        if node.id in stats.unlocked_nodes:
            return PurchaseResult(False, f"You already know {node.name}.", node)

        unlocked = set(stats.unlocked_nodes)
        missing = [p for p in node.prerequisites if p not in unlocked]
        if missing:
            names = ", ".join(self._display_name(p) for p in missing)
            return PurchaseResult(False, f"You must train {names} first.", node)

        if stats.skill_points < node.cost:
            return PurchaseResult(
                False,
                f"{node.name} costs {node.cost} skill "
                f"{_points(node.cost)}; you have {stats.skill_points}.",
                node,
            )

        # Commit the purchase: spend points, record the node, set every unlock
        # flag. Reassign the JSON columns (not in-place mutate) so SQLAlchemy
        # detects the change — same discipline as PlayerStats.skills / flags.
        stats.skill_points -= node.cost
        stats.unlocked_nodes = [*stats.unlocked_nodes, node.id]
        ctx.player_repo.save_stats(stats)
        new_flags = dict(ctx.player.flags)
        for flag in node.unlock.flags:
            new_flags[flag] = True
        ctx.player.flags = new_flags
        return PurchaseResult(True, f"You train {node.name}.", node)

    def _display_name(self, node_id: str) -> str:
        node = self._registry.get(node_id)
        return node.name if node is not None else node_id


def _points(cost: int) -> str:
    return "point" if cost == 1 else "points"
