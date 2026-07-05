"""Meta commands."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandRegistry, CommandScope
from lorecraft.features.npc.dialogue import _NPC_KEY
from lorecraft.engine.services.save import SaveSlotService

# Dialogue reply commands are only meaningful while in an active conversation.
_DIALOGUE_ONLY_VERBS = frozenset({"choice", "bye"})


def _build_command_help(registry: CommandRegistry, verb: str) -> list[str]:
    """Detailed help for one command (issue-7502f412: `help <command>`).

    Looks the verb up (including its aliases), and returns its usage/help text,
    aliases, and scope. Returns a not-found line if the verb is unknown, so the
    player gets useful feedback rather than the full list.
    """
    command = registry.get(verb)
    if command is None:
        return [
            f"No help for '{verb}' — unknown command.",
            "Type 'help' for the full list of commands.",
        ]

    lines = [command.help_text or f"{command.verb} — (no description available)"]
    # All the other ways to invoke this command (primary verb + aliases),
    # minus the one the player typed.
    other_names = [name for name in (command.verb, *command.aliases) if name != verb]
    if other_names:
        lines.append(f"  Aliases: {', '.join(other_names)}")
    lines.append(f"  Scope: {command.scope.value}")
    return lines


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
        help="help [command] — list commands, or show detail for one",
    )
    def help_command(noun: str | None, ctx: GameContext) -> None:
        target = (noun or "").strip().split()[0] if noun and noun.strip() else None
        if target:
            # `help <command>` — detailed help for a specific command.
            ctx.say("\n".join(_build_command_help(registry, target.lower())))
        else:
            ctx.say("\n".join(_build_help_lines(registry, ctx)))

    @registry.register(
        "quit",
        scope=CommandScope.GLOBAL,
        help="quit — return to the lobby",
    )
    def quit_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        ctx.say("Goodbye.")
        ctx.tell_room(f"{ctx.player.username} leaves the game.")
        ctx.push_update("disconnect", True)

    @registry.register(
        "save",
        scope=CommandScope.GLOBAL,
        help="save [slot] — save your progress",
    )
    def save_command(noun: str | None, ctx: GameContext) -> None:
        service.save(noun, ctx)

    @registry.register(
        "load",
        scope=CommandScope.GLOBAL,
        help="load [slot] — load a saved game",
    )
    def load_command(noun: str | None, ctx: GameContext) -> None:
        service.load(noun, ctx)
