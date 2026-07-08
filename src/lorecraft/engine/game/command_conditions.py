"""Command condition registry: pluggable predicates for command availability.

See docs/feature-registration.md for the complete feature registration pattern,
which shows how to plug new condition predicates (combat.has_combat_target, etc.)
without touching core engine code.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lorecraft.engine.game.holders import Location

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConditionResult:
    """Result of evaluating a condition: allowed or not, with optional reason."""

    allowed: bool
    reason: str | None = None


ConditionHandler = Callable[[str, "GameContext"], ConditionResult]


class CommandConditionRegistry:
    """Registry of command condition predicates.

    Built-in conditions (requires_light, not_in_combat, etc.) are
    registered at module load. New conditions can be registered without
    touching registry.py, enabling custom gates like level checks, quest
    state, NPC mood, etc.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ConditionHandler] = {}

    def register(self, condition_name: str, handler: ConditionHandler) -> None:
        """Register a condition handler by name."""
        self._handlers[condition_name] = handler

    def evaluate(self, condition: str, ctx: "GameContext") -> ConditionResult:
        """Evaluate a single condition string (format: "name" or "name:param").

        Unknown conditions default to allowed=True (safe fallback for
        forward-compatible command definitions). Handlers should return
        ConditionResult(False, reason) to prevent the command.
        """
        name, _, parameter = condition.partition(":")
        if name not in self._handlers:
            return ConditionResult(True)
        handler = self._handlers[name]
        try:
            return handler(parameter, ctx)
        except Exception:
            # A buggy predicate must not crash command dispatch, but the
            # failure has to leave a trace — otherwise the command silently
            # becomes unavailable with a generic message and no diagnostics.
            log.exception("command_condition_failed condition=%s", name)
            return ConditionResult(False, "Condition evaluation error.")

    def __contains__(self, condition_name: str) -> bool:
        return condition_name in self._handlers


_registry = CommandConditionRegistry()


def _light_check(parameter: str, ctx: "GameContext") -> ConditionResult:
    del parameter
    if ctx.room.light_level > 0:
        return ConditionResult(True)
    if _has_lit_equipped_source(ctx):
        return ConditionResult(True)
    return ConditionResult(False, "It's too dark to do that. You need a light.")


def _has_lit_equipped_source(ctx: "GameContext") -> bool:
    from lorecraft.engine.models.items import ItemInstance
    from lorecraft.engine.services.item_components import get_component_state

    for stack in ctx.stack_repo.stacks_for_owner("player", ctx.player.id):
        if stack.slot is None or stack.instance_id is None:
            continue
        item = ctx.item_repo.get(stack.item_id)
        if item is None or item.light <= 0:
            continue
        instance = ctx.session.get(ItemInstance, stack.instance_id)
        if instance is None:
            continue
        lit_state = get_component_state(instance, "lit")
        if isinstance(lit_state, dict) and lit_state.get("lit"):
            return True
    return False


def _not_in_combat_check(parameter: str, ctx: "GameContext") -> ConditionResult:
    del parameter
    if ctx.player.active_combat_session_id:
        return ConditionResult(False, "You can't do that while in combat.")
    return ConditionResult(True)


def _in_combat_check(parameter: str, ctx: "GameContext") -> ConditionResult:
    del parameter
    if not ctx.player.active_combat_session_id:
        return ConditionResult(False, "You aren't in combat.")
    return ConditionResult(True)


def _flag_set_check(parameter: str, ctx: "GameContext") -> ConditionResult:
    if not parameter or not ctx.player.flags.get(parameter):
        return ConditionResult(False, "You can't do that yet.")
    return ConditionResult(True)


def _flag_not_set_check(parameter: str, ctx: "GameContext") -> ConditionResult:
    if parameter and ctx.player.flags.get(parameter):
        return ConditionResult(False, "You can't do that anymore.")
    return ConditionResult(True)


def _item_in_inventory_check(parameter: str, ctx: "GameContext") -> ConditionResult:
    if parameter and (
        ctx.stack_repo.quantity_of(Location("player", ctx.player.id), parameter) <= 0
    ):
        return ConditionResult(False, "You don't have the required item.")
    return ConditionResult(True)


def _object_present_check(parameter: str, ctx: "GameContext") -> ConditionResult:
    """`object_present:<item_id>` — the item is in the current room *or* held by
    the player. The presence gate for Sprint 55 context-attached commands (a
    `pull` lever, a `read` inscription): a context verb carries this so it is
    available — and, via the help-availability filter, only *listed* — when its
    object is at hand."""
    if not parameter:
        return ConditionResult(False, "There's nothing like that here.")
    in_room = ctx.stack_repo.quantity_of(Location("room", ctx.room.id), parameter) > 0
    held = ctx.stack_repo.quantity_of(Location("player", ctx.player.id), parameter) > 0
    if in_room or held:
        return ConditionResult(True)
    return ConditionResult(False, "There's nothing like that here.")


def _npc_present_check(parameter: str, ctx: "GameContext") -> ConditionResult:
    """`npc_present:<npc_id>` — the NPC is in the current room. The NPC-carrier
    half of the Sprint 55 presence gate (`pet` the dog, `bribe` the guard)."""
    if not parameter:
        return ConditionResult(False, "They aren't here.")
    if any(npc.id == parameter for npc in ctx.npc_repo.in_room(ctx.room.id)):
        return ConditionResult(True)
    return ConditionResult(False, "They aren't here.")


_registry.register("requires_light", _light_check)
_registry.register("not_in_combat", _not_in_combat_check)
_registry.register("in_combat", _in_combat_check)
_registry.register("flag_set", _flag_set_check)
_registry.register("flag_not_set", _flag_not_set_check)
_registry.register("item_in_inventory", _item_in_inventory_check)
_registry.register("object_present", _object_present_check)
_registry.register("npc_present", _npc_present_check)


def get_registry() -> CommandConditionRegistry:
    """Get the global command condition registry."""
    return _registry
