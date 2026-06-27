"""Command registration and condition evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from collections.abc import Callable

from lorecraft.types import CommandContext


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


CommandHandler = Callable[[str | None, object], None]


@dataclass(frozen=True)
class CommandDefinition:
    verb: str
    handler: CommandHandler
    aliases: tuple[str, ...] = ()
    scope: CommandScope = CommandScope.WORLD
    conditions: tuple[str | CommandCondition, ...] = ()


@dataclass(frozen=True)
class ConditionResult:
    allowed: bool
    reason: str | None = None


@dataclass
class CommandRegistry:
    _commands: dict[str, CommandDefinition] = field(default_factory=dict)

    def register(
        self,
        verb: str,
        *aliases: str,
        scope: CommandScope = CommandScope.WORLD,
        conditions: list[str | CommandCondition] | None = None,
    ) -> Callable[[CommandHandler], CommandHandler]:
        def decorator(handler: CommandHandler) -> CommandHandler:
            definition = CommandDefinition(
                verb=verb,
                aliases=tuple(aliases),
                scope=scope,
                conditions=tuple(conditions or ()),
                handler=handler,
            )
            for key in (verb, *aliases):
                self._commands[key] = definition
            return handler

        return decorator

    def get(self, verb: str) -> CommandDefinition | None:
        return self._commands.get(verb)

    def evaluate_conditions(
        self, command: CommandDefinition, ctx: CommandContext
    ) -> ConditionResult:
        disabled = set(getattr(ctx.room, "disabled_commands", []) or [])
        if command.verb in disabled:
            return ConditionResult(False, "You can't do that here.")

        for condition in command.conditions:
            result = _evaluate_condition(str(condition), ctx)
            if not result.allowed:
                return result
        return ConditionResult(True)


def _evaluate_condition(condition: str, ctx: CommandContext) -> ConditionResult:
    name, _, parameter = condition.partition(":")

    if name == CommandCondition.REQUIRES_LIGHT:
        if getattr(ctx.room, "light_level", 1) <= 0:
            return ConditionResult(False, "It's too dark to do that.")
    elif name == CommandCondition.NOT_IN_COMBAT:
        if getattr(ctx.player, "active_combat_session_id", None):
            return ConditionResult(False, "You can't do that while in combat.")
    elif name == CommandCondition.IN_COMBAT:
        if not getattr(ctx.player, "active_combat_session_id", None):
            return ConditionResult(False, "You aren't in combat.")
    elif name == CommandCondition.FLAG_SET:
        if not parameter or not getattr(ctx.player, "flags", {}).get(parameter):
            return ConditionResult(False, "You can't do that yet.")
    elif name == CommandCondition.FLAG_NOT_SET:
        if parameter and getattr(ctx.player, "flags", {}).get(parameter):
            return ConditionResult(False, "You can't do that anymore.")
    elif name == CommandCondition.ITEM_IN_INVENTORY:
        if parameter and parameter not in getattr(ctx.player, "inventory", []):
            return ConditionResult(False, "You don't have the required item.")

    return ConditionResult(True)
