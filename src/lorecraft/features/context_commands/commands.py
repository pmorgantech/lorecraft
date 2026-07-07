"""Context-attached command dispatcher (Sprint 55.3).

Registers, for each distinct context verb, ONE command into the flat
`CommandRegistry`, gated by a `context_verb:<verb>` availability condition
(true when *some* declaring object is present + its `requires` passes). The
handler resolves which present object the verb applies to — the noun
disambiguates when several share a verb (`pull rusty` vs `pull brass`) — and
fires that object's `side_effects` through the shared side-effect registry.
Availability rides the existing help filter, so a context verb is listed only
when in context. A verb/alias that would shadow an already-registered command
is skipped with a dev-time warning (the wishlist's "avoid duplicate aliases").
"""

from __future__ import annotations

import logging

from lorecraft.engine.game import command_conditions
from lorecraft.engine.game.command_conditions import ConditionResult
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.models.world import NPC
from lorecraft.features.context_commands.models import (
    ContextBinding,
    ContextCommandRegistry,
    get_registry,
)
from lorecraft.features.npc.side_effects import get_registry as get_side_effect_registry

log = logging.getLogger(__name__)

CONTEXT_VERB_CONDITION = "context_verb"


def _requires_ok(binding: ContextBinding, ctx: GameContext) -> bool:
    if not binding.requires:
        return True
    return command_conditions.get_registry().evaluate(binding.requires, ctx).allowed


def _available_bindings(
    verb: str, ctx: GameContext, registry: ContextCommandRegistry
) -> list[ContextBinding]:
    """Bindings for `verb` whose object is present and whose `requires` passes."""
    conditions = command_conditions.get_registry()
    return [
        binding
        for binding in registry.bindings_for(verb)
        if conditions.evaluate(binding.gate, ctx).allowed and _requires_ok(binding, ctx)
    ]


def _noun_matches(binding: ContextBinding, needle: str, ctx: GameContext) -> bool:
    if needle == binding.owner_id.lower():
        return True
    if binding.owner_type == "item":
        item = ctx.item_repo.get(binding.owner_id)
        names = [item.name, *item.aliases] if item is not None else []
    else:
        npc = ctx.session.get(NPC, binding.owner_id)
        names = [npc.name] if npc is not None else []
    return any(needle in name.lower() for name in names)


def _make_handler(verb: str, registry: ContextCommandRegistry):
    def handler(noun: str | None, ctx: GameContext) -> None:
        candidates = _available_bindings(verb, ctx, registry)
        if not candidates:
            # Defensive: the gating condition normally blocks this first.
            ctx.say("You can't do that here.")
            return
        needle = (noun or "").strip().lower()
        if needle:
            narrowed = [b for b in candidates if _noun_matches(b, needle, ctx)]
            if narrowed:
                candidates = narrowed
        binding = candidates[0]
        if binding.say:
            ctx.say(binding.say)
        get_side_effect_registry().apply(binding.side_effects, ctx)

    return handler


def _register_availability_condition(registry: ContextCommandRegistry) -> None:
    def _available(verb: str, ctx: GameContext) -> ConditionResult:
        if _available_bindings(verb, ctx, registry):
            return ConditionResult(True)
        return ConditionResult(False, "You can't do that here.")

    command_conditions.get_registry().register(CONTEXT_VERB_CONDITION, _available)


def register_context_commands(
    command_registry: CommandRegistry,
    context_registry: ContextCommandRegistry | None = None,
) -> None:
    """Wire every distinct context verb into the command registry. Call after
    the built-in verbs are registered so collisions are detected."""
    context_registry = context_registry or get_registry()
    _register_availability_condition(context_registry)

    for verb in context_registry.verbs():
        existing = command_registry.get(verb)
        if existing is not None:
            log.warning(
                "context command %r shadows existing command %r; skipping",
                verb,
                existing.verb,
            )
            continue
        bindings = context_registry.bindings_for(verb)
        # Union of declared aliases, minus any that already resolve to a command.
        aliases: list[str] = []
        for binding in bindings:
            for alias in binding.aliases:
                if alias not in aliases and command_registry.get(alias) is None:
                    aliases.append(alias)
        help_text = next(
            (b.help for b in bindings if b.help),
            f"{verb} — interact with something here",
        )
        command_registry.register(
            verb,
            *aliases,
            conditions=[f"{CONTEXT_VERB_CONDITION}:{verb}"],
            help=help_text,
            category="exploration",
        )(_make_handler(verb, context_registry))
