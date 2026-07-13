"""Progression player verbs: `train`/`learn` (spend skill points) and the
read-only `abilities` query (Sprint 74.3 + 74.8).

`train` with no argument lists what you can buy now (and what remains locked);
with a node id it attempts the purchase via `SkillTreeService`. `abilities`
mirrors the read-only `quests` command — it reports owned abilities and what is
currently trainable, without mutating anything.
"""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.features.progression.service import SkillTreeService
from lorecraft.features.progression.skill_tree import SkillTreeNode


def _skill_points(ctx: GameContext) -> int:
    stats = ctx.player_repo.stats(ctx.player.id)
    return stats.skill_points if stats is not None else 0


def _node_line(node: SkillTreeNode, *, marker: str) -> str:
    cost = f"{node.cost} sp"
    return f"  {marker} {node.name} ({cost}) — {node.description.strip()}"


def register_progression_commands(
    registry: CommandRegistry, service: SkillTreeService | None = None
) -> None:
    tree = service or SkillTreeService()

    @registry.register(
        "train",
        "learn",
        help="train [ability] — spend skill points to unlock an ability (no arg lists them)",
    )
    def train_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            _list_trainable(tree, ctx)
            return
        result = tree.purchase(ctx, noun.strip())
        if result.ok:
            ctx.say(result.reason, MessageType.LEVEL)
            ctx.push_update("skill_points", _skill_points(ctx))
        else:
            ctx.say(result.reason, MessageType.WARNING)

    @registry.register(
        "abilities",
        "abils",
        help="abilities — list abilities you know and can currently train",
    )
    def abilities_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        owned = tree.owned_nodes(ctx)
        available = tree.available_nodes(ctx)
        ctx.say(
            f"Skill points: {_skill_points(ctx)}.",
            MessageType.SYSTEM,
        )
        if owned:
            ctx.say("Abilities you know:", MessageType.SYSTEM)
            for node in owned:
                ctx.say(_node_line(node, marker="✓"), MessageType.SYSTEM)
        else:
            ctx.say("You have not trained any abilities yet.", MessageType.SYSTEM)
        if available:
            ctx.say("Ready to train:", MessageType.SYSTEM)
            for node in available:
                ctx.say(_node_line(node, marker="•"), MessageType.SYSTEM)


def _list_trainable(tree: SkillTreeService, ctx: GameContext) -> None:
    available = tree.available_nodes(ctx)
    locked = tree.locked_nodes(ctx)
    ctx.say(f"Skill points: {_skill_points(ctx)}.", MessageType.SYSTEM)
    if available:
        ctx.say("You can train:", MessageType.SYSTEM)
        for node in available:
            ctx.say(_node_line(node, marker="•"), MessageType.SYSTEM)
    else:
        ctx.say("Nothing is ready to train right now.", MessageType.SYSTEM)
    if locked:
        ctx.say("Still locked (need prerequisites or more points):", MessageType.SYSTEM)
        for node in locked:
            ctx.say(_node_line(node, marker="✗"), MessageType.SYSTEM)
