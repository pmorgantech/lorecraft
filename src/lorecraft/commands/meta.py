"""Meta commands."""

from __future__ import annotations

from typing import cast

from lorecraft.game.context import GameContext
from lorecraft.game.registry import CommandRegistry, CommandScope
from lorecraft.npc.dialogue import _NPC_KEY
from lorecraft.services.save import SaveSlotService

# Dialogue reply commands are only meaningful while in an active conversation.
_DIALOGUE_ONLY_VERBS = frozenset({"choice", "bye"})


def _build_help_lines(registry: CommandRegistry, ctx: GameContext) -> list[str]:
    in_dialogue = bool(ctx.player.flags.get(_NPC_KEY))
    in_combat = bool(ctx.player.active_combat_session_id)

    if in_dialogue:
        lines = ["You are in conversation. Available commands:"]
    elif in_combat:
        lines = ["You are in combat. Available commands:"]
    else:
        lines = ["Available commands:"]

    for command in registry.all_commands():
        if not command.help_text:
            continue
        if in_dialogue and command.scope not in (
            CommandScope.GLOBAL,
            CommandScope.SOCIAL,
        ):
            continue
        if not in_dialogue and command.verb in _DIALOGUE_ONLY_VERBS:
            continue
        if not registry.evaluate_conditions(command, ctx).allowed:
            continue
        lines.append(f"  {command.help_text}")

    return lines


def register_meta_commands(
    registry: CommandRegistry, save_service: SaveSlotService | None = None
) -> None:
    service = save_service or SaveSlotService()

    @registry.register(
        "help",
        "?",
        scope=CommandScope.GLOBAL,
        help="help — show this list",
    )
    def help_command(noun: str | None, ctx: object) -> None:
        del noun
        game_ctx = cast(GameContext, ctx)
        game_ctx.say("\n".join(_build_help_lines(registry, game_ctx)))

    @registry.register(
        "quit",
        scope=CommandScope.GLOBAL,
        help="quit — return to the lobby",
    )
    def quit_command(noun: str | None, ctx: object) -> None:
        del noun
        game_ctx = cast(GameContext, ctx)
        game_ctx.say("Goodbye.")
        game_ctx.tell_room(f"{game_ctx.player.username} leaves the game.")
        game_ctx.push_update("disconnect", True)

    @registry.register(
        "save",
        scope=CommandScope.GLOBAL,
        help="save [slot] — save your progress",
    )
    def save_command(noun: str | None, ctx: object) -> None:
        service.save(noun, cast(GameContext, ctx))

    @registry.register(
        "load",
        scope=CommandScope.GLOBAL,
        help="load [slot] — load a saved game",
    )
    def load_command(noun: str | None, ctx: object) -> None:
        service.load(noun, cast(GameContext, ctx))
