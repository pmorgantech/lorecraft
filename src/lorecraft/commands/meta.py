"""Meta commands."""

from __future__ import annotations

from typing import cast

from lorecraft.game.context import GameContext
from lorecraft.game.registry import CommandRegistry, CommandScope
from lorecraft.services.save import SaveSlotService


def register_meta_commands(
    registry: CommandRegistry, save_service: SaveSlotService | None = None
) -> None:
    service = save_service or SaveSlotService()

    @registry.register("help", "?", scope=CommandScope.GLOBAL)
    def help_command(noun: str | None, ctx: object) -> None:
        del noun
        game_ctx = cast(GameContext, ctx)
        game_ctx.say(
            "Available commands: help, quit (returns to lobby), save [slot], load [slot], look, "
            "examine <item>, take <item>, drop <item>, inventory, go <direction>, "
            "north, south, east, west."
        )

    @registry.register("quit", scope=CommandScope.GLOBAL)
    def quit_command(noun: str | None, ctx: object) -> None:
        del noun
        game_ctx = cast(GameContext, ctx)
        game_ctx.say("Goodbye.")
        game_ctx.push_update("disconnect", True)

    @registry.register("save", scope=CommandScope.GLOBAL)
    def save_command(noun: str | None, ctx: object) -> None:
        service.save(noun, cast(GameContext, ctx))

    @registry.register("load", scope=CommandScope.GLOBAL)
    def load_command(noun: str | None, ctx: object) -> None:
        service.load(noun, cast(GameContext, ctx))
