"""Command registration and condition evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from lorecraft.engine.game.command_conditions import ConditionResult, get_registry
from lorecraft.engine.game.context import GameContext
from lorecraft.types import CommandHandler


class CommandScope(StrEnum):
    GLOBAL = "global"
    SOCIAL = "social"
    WORLD = "world"


class CommandCondition(StrEnum):
    REQUIRES_LIGHT = "requires_light"
    NOT_IN_COMBAT = "not_in_combat"
    IN_COMBAT = "in_combat"
    HAS_COMBAT_TARGET = "has_combat_target"
    FLAG_SET = "flag_set"
    FLAG_NOT_SET = "flag_not_set"
    ITEM_IN_INVENTORY = "item_in_inventory"
    NPC_PRESENT = "npc_present"


@dataclass(frozen=True)
class CommandDefinition:
    verb: str
    handler: CommandHandler
    aliases: tuple[str, ...] = ()
    scope: CommandScope = CommandScope.WORLD
    conditions: tuple[str | CommandCondition, ...] = ()
    help_text: str = ""


@dataclass
class CommandRegistry:
    _commands: dict[str, CommandDefinition] = field(default_factory=dict)
    _order: list[CommandDefinition] = field(default_factory=list)

    def register(
        self,
        verb: str,
        *aliases: str,
        scope: CommandScope = CommandScope.WORLD,
        conditions: list[str | CommandCondition] | None = None,
        help: str = "",
    ) -> Callable[[CommandHandler], CommandHandler]:
        def decorator(handler: CommandHandler) -> CommandHandler:
            definition = CommandDefinition(
                verb=verb,
                aliases=tuple(aliases),
                scope=scope,
                conditions=tuple(conditions or ()),
                handler=handler,
                help_text=help,
            )
            for key in (verb, *aliases):
                self._commands[key] = definition
            self._order.append(definition)
            return handler

        return decorator

    def get(self, verb: str) -> CommandDefinition | None:
        return self._commands.get(verb)

    def all_commands(self) -> list[CommandDefinition]:
        """Distinct registered commands in registration order (aliases deduplicated)."""
        return list(self._order)

    def evaluate_conditions(
        self, command: CommandDefinition, ctx: GameContext
    ) -> ConditionResult:
        """Evaluate all conditions on a command using the registry."""
        disabled = set(ctx.room.disabled_commands or [])
        if command.verb in disabled:
            return ConditionResult(False, "You can't do that here.")

        registry = get_registry()
        for condition in command.conditions:
            result = registry.evaluate(str(condition), ctx)
            if not result.allowed:
                return result
        return ConditionResult(True)
