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
from lorecraft.engine.scripting.vocabulary import (
    FLAG_PARAM,
    CapabilitySig,
    ParamSpec,
    Subject,
    VocabEntry,
    VocabKind,
    global_vocabulary,
)

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
        """Register a condition handler by name (no catalog descriptor)."""
        self._handlers[condition_name] = handler

    def register_spec(self, spec: VocabEntry, handler: ConditionHandler) -> None:
        """Register a handler *and* publish its descriptor to the shared catalog.

        See ``docs/scripting_engine_design.md`` §8. An exact-name collision in the shared
        catalog raises ``VocabularyError`` rather than silently overwriting.
        """
        global_vocabulary().register(spec)
        self._handlers[spec.name] = handler

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


def _actor_has_flag_check(parameter: str, ctx: "GameContext") -> ConditionResult:
    if not parameter or not ctx.player.flags.get(parameter):
        return ConditionResult(False, "You can't do that yet.")
    return ConditionResult(True)


def _actor_lacks_flag_check(parameter: str, ctx: "GameContext") -> ConditionResult:
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


def _condition(
    name: str,
    *,
    subject: Subject,
    category: str,
    domain: str,
    attribute: str,
    op: str,
    doc: str,
    params: tuple[ParamSpec, ...] = (),
) -> VocabEntry:
    return VocabEntry(
        name=name,
        kind=VocabKind.CONDITION,
        subject=subject,
        category=category,
        doc=doc,
        capability=CapabilitySig(subject, domain, attribute, op),
        params=params,
    )


_registry.register_spec(
    _condition(
        "requires_light",
        subject=Subject.SELF,
        category="environment",
        domain="light",
        attribute="level",
        op="at_least",
        doc="The room is lit, or the actor carries a lit light source.",
    ),
    _light_check,
)
_registry.register_spec(
    _condition(
        "not_in_combat",
        subject=Subject.ACTOR,
        category="combat",
        domain="combat",
        attribute="session",
        op="lacks",
        doc="The actor is not currently in a combat session.",
    ),
    _not_in_combat_check,
)
_registry.register_spec(
    _condition(
        "in_combat",
        subject=Subject.ACTOR,
        category="combat",
        domain="combat",
        attribute="session",
        op="has",
        doc="The actor is currently in a combat session.",
    ),
    _in_combat_check,
)
# `actor_has_flag`/`actor_lacks_flag` register on BOTH the command and dialogue surfaces with an
# IDENTICAL descriptor (see features/npc/dialogue_conditions.py) — same capability, so the
# catalog's idempotent registration keeps one entry. The descriptor must match byte-for-byte on
# both sides or the generated `docs/worldbuilding/scripting_api.md` would depend on import order.
_registry.register_spec(
    _condition(
        "actor_has_flag",
        subject=Subject.ACTOR,
        category="flags",
        domain="flags",
        attribute="<flag>",
        op="has",
        doc="The actor has the named flag(s) set.",
        params=(FLAG_PARAM,),
    ),
    _actor_has_flag_check,
)
_registry.register_spec(
    _condition(
        "actor_lacks_flag",
        subject=Subject.ACTOR,
        category="flags",
        domain="flags",
        attribute="<flag>",
        op="lacks",
        doc="The actor does not have the named flag(s) set.",
        params=(FLAG_PARAM,),
    ),
    _actor_lacks_flag_check,
)
_registry.register_spec(
    _condition(
        "item_in_inventory",
        subject=Subject.ACTOR,
        category="inventory",
        domain="inventory",
        attribute="item",
        op="has",
        doc="The actor carries at least one of the named item.",
        params=(ParamSpec("item_id", "item_id", doc="Item id (colon-string param)."),),
    ),
    _item_in_inventory_check,
)
_registry.register_spec(
    _condition(
        "object_present",
        subject=Subject.SELF,
        category="presence",
        domain="presence",
        attribute="item",
        op="has",
        doc="The named item is in the current room or held by the actor.",
        params=(ParamSpec("item_id", "item_id", doc="Item id (colon-string param)."),),
    ),
    _object_present_check,
)
_registry.register_spec(
    _condition(
        "npc_present",
        subject=Subject.SELF,
        category="presence",
        domain="presence",
        attribute="npc",
        op="has",
        doc="The named NPC is in the current room.",
        params=(ParamSpec("npc_id", "npc_id", doc="NPC id (colon-string param)."),),
    ),
    _npc_present_check,
)


def get_registry() -> CommandConditionRegistry:
    """Get the global command condition registry."""
    return _registry
