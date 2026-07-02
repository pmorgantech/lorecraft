"""Command registration and condition evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from collections.abc import Callable
from typing import Any, cast


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
    help_text: str = ""


@dataclass(frozen=True)
class ConditionResult:
    allowed: bool
    reason: str | None = None


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
        self, command: CommandDefinition, ctx: object
    ) -> ConditionResult:
        ctx_any = cast(Any, ctx)
        disabled = set(getattr(ctx_any.room, "disabled_commands", []) or [])
        if command.verb in disabled:
            return ConditionResult(False, "You can't do that here.")

        for condition in command.conditions:
            result = _evaluate_condition(str(condition), ctx)
            if not result.allowed:
                return result
        return ConditionResult(True)


def _evaluate_condition(condition: str, ctx: object) -> ConditionResult:
    name, _, parameter = condition.partition(":")
    ctx_any = cast(Any, ctx)

    if name == CommandCondition.REQUIRES_LIGHT:
        if getattr(ctx_any.room, "light_level", 1) <= 0:
            return ConditionResult(False, "It's too dark to do that.")
    elif name == CommandCondition.NOT_IN_COMBAT:
        if getattr(ctx_any.player, "active_combat_session_id", None):
            return ConditionResult(False, "You can't do that while in combat.")
    elif name == CommandCondition.IN_COMBAT:
        if not getattr(ctx_any.player, "active_combat_session_id", None):
            return ConditionResult(False, "You aren't in combat.")
    elif name == CommandCondition.FLAG_SET:
        if not parameter or not getattr(ctx_any.player, "flags", {}).get(parameter):
            return ConditionResult(False, "You can't do that yet.")
    elif name == CommandCondition.FLAG_NOT_SET:
        if parameter and getattr(ctx_any.player, "flags", {}).get(parameter):
            return ConditionResult(False, "You can't do that anymore.")
    elif name == CommandCondition.ITEM_IN_INVENTORY:
        if parameter and parameter not in getattr(ctx_any.player, "inventory", []):
            return ConditionResult(False, "You don't have the required item.")

    return ConditionResult(True)
