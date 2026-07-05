"""Meta commands."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import (
    CommandDefinition,
    CommandRegistry,
    CommandScope,
)
from lorecraft.features.npc.dialogue import _NPC_KEY
from lorecraft.engine.services.save import SaveSlotService

# Dialogue reply commands are only meaningful while in an active conversation.
_DIALOGUE_ONLY_VERBS = frozenset({"choice", "bye"})

# The short list bare `help` shows in normal play — the verbs a new player needs
# first. Filtered to what's actually registered and currently available.
_CRITICAL_COMMANDS = (
    "look",
    "go",
    "take",
    "drop",
    "inventory",
    "examine",
    "say",
    "score",
)

# Display order + human labels for the `help commands` grouping. Categories are
# set at registration (see `register_all_commands`); anything unlisted falls to
# the end under "Other".
_CATEGORY_ORDER = (
    "system",
    "movement",
    "social",
    "inventory",
    "exploration",
    "character",
    "condition",
    "economy",
    "banking",
    "trading",
    "transit",
    "general",
)
_CATEGORY_LABELS = {
    "system": "System",
    "movement": "Movement",
    "social": "Social",
    "inventory": "Items & Inventory",
    "exploration": "Exploration",
    "character": "Character",
    "condition": "Condition",
    "economy": "Trade & Economy",
    "banking": "Banking",
    "trading": "Player Trading",
    "transit": "Travel & Transit",
    "general": "Other",
}


def _is_available(
    registry: CommandRegistry,
    command: CommandDefinition,
    ctx: GameContext,
    *,
    in_dialogue: bool,
) -> bool:
    """Whether a command should be shown to the player right now."""
    if not command.help_text:
        return False
    if in_dialogue and command.scope not in (CommandScope.GLOBAL, CommandScope.SOCIAL):
        return False
    if not in_dialogue and command.verb in _DIALOGUE_ONLY_VERBS:
        return False
    return registry.evaluate_conditions(command, ctx).allowed


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
            "Type 'help' for common commands, or 'help commands' for the full list.",
        ]

    lines = [command.help_text or f"{command.verb} — (no description available)"]
    # All the other ways to invoke this command (primary verb + aliases),
    # minus the one the player typed.
    other_names = [name for name in (command.verb, *command.aliases) if name != verb]
    if other_names:
        lines.append(f"  Aliases: {', '.join(other_names)}")
    lines.append(f"  Category: {command.category}")
    lines.append(f"  Scope: {command.scope.value}")
    return lines


def _build_curated_help(registry: CommandRegistry, ctx: GameContext) -> list[str]:
    """Bare `help` in normal play: the most critical commands + pointers."""
    lines = ["Common commands:"]
    for verb in _CRITICAL_COMMANDS:
        command = registry.get(verb)
        if command is not None and _is_available(
            registry, command, ctx, in_dialogue=False
        ):
            lines.append(f"  {command.help_text}")
    lines.append("")
    lines.append("Type 'help commands' for the full list (by category),")
    lines.append("or 'help <command>' for detail on a specific command.")
    return lines


def _build_commands_by_category(
    registry: CommandRegistry, ctx: GameContext
) -> list[str]:
    """`help commands`: every available command, grouped by category and
    alphabetized within each group."""
    in_dialogue = bool(ctx.player.flags.get(_NPC_KEY))
    groups: dict[str, list[CommandDefinition]] = {}
    for command in registry.all_commands():
        if not _is_available(registry, command, ctx, in_dialogue=in_dialogue):
            continue
        groups.setdefault(command.category, []).append(command)

    lines = ["All commands (type 'help <command>' for detail):"]
    # Known categories first (in a sensible order), then any leftovers A-Z.
    ordered = list(_CATEGORY_ORDER) + sorted(
        c for c in groups if c not in _CATEGORY_ORDER
    )
    for category in ordered:
        commands = groups.get(category)
        if not commands:
            continue
        label = _CATEGORY_LABELS.get(category, category.capitalize())
        lines.append("")
        lines.append(f"{label}:")
        for command in sorted(commands, key=lambda c: c.verb):
            lines.append(f"  {command.help_text}")
    return lines


def _build_help_lines(registry: CommandRegistry, ctx: GameContext) -> list[str]:
    """Context-scoped command list, shown for bare `help` during dialogue/combat."""
    in_dialogue = bool(ctx.player.flags.get(_NPC_KEY))
    in_combat = bool(ctx.player.active_combat_session_id)

    if in_dialogue:
        lines = ["You are in conversation. Available commands:"]
    elif in_combat:
        lines = ["You are in combat. Available commands:"]
    else:
        lines = ["Available commands:"]

    for command in registry.all_commands():
        if _is_available(registry, command, ctx, in_dialogue=in_dialogue):
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
        help="help [command|commands] — common commands, the full list, or detail on one",
    )
    def help_command(noun: str | None, ctx: GameContext) -> None:
        arg = (noun or "").strip()
        first = arg.split()[0].lower() if arg else ""
        in_dialogue = bool(ctx.player.flags.get(_NPC_KEY))
        in_combat = bool(ctx.player.active_combat_session_id)

        if not first:
            # In a modal context (dialogue/combat) the scoped list is more
            # useful; otherwise show the curated quick-start set.
            if in_dialogue or in_combat:
                ctx.say("\n".join(_build_help_lines(registry, ctx)))
            else:
                ctx.say("\n".join(_build_curated_help(registry, ctx)))
        elif first in ("commands", "all"):
            ctx.say("\n".join(_build_commands_by_category(registry, ctx)))
        else:
            # `help <command>` — detailed help for a specific command.
            ctx.say("\n".join(_build_command_help(registry, first)))

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
