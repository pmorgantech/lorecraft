"""Meta commands."""

from __future__ import annotations

from typing import cast

from lorecraft.game.context import GameContext
from lorecraft.game.registry import CommandRegistry, CommandScope


def register_meta_commands(registry: CommandRegistry) -> None:
    @registry.register("help", "?", scope=CommandScope.GLOBAL)
    def help_command(noun: str | None, ctx: object) -> None:
        del noun
        game_ctx = cast(GameContext, ctx)
        game_ctx.say(
            "Available commands: help, quit, look, examine <item>, take <item>, "
            "drop <item>, inventory, go <direction>, north, south, east, west."
        )

    @registry.register("quit", scope=CommandScope.GLOBAL)
    def quit_command(noun: str | None, ctx: object) -> None:
        del noun
        game_ctx = cast(GameContext, ctx)
        game_ctx.say("Goodbye.")
        game_ctx.push_update("disconnect", True)
