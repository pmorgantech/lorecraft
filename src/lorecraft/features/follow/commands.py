"""Follow commands: follow / unfollow (Sprint 47)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.features.follow.service import FollowService


def register_follow_commands(
    registry: CommandRegistry, follow_service: FollowService | None = None
) -> None:
    service = follow_service or FollowService()

    @registry.register(
        "follow",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="follow <player> — move with a player when they move (bare `follow` shows status)",
    )
    def follow_command(noun: str | None, ctx: GameContext) -> None:
        service.follow(noun, ctx)

    @registry.register(
        "unfollow",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="unfollow — stop following whoever you were following",
    )
    def unfollow_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        service.unfollow(ctx)
