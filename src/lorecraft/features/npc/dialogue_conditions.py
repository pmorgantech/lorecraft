"""Dialogue choice/exit condition registry: pluggable predicates for visibility.

See docs/feature-registration.md for the complete feature registration pattern,
which shows how to plug new predicates (combat.has_combat_target, etc.) for
dialogue conditions without touching dialogue.py.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from lorecraft.engine.scripting.vocabulary import (
    FLAG_PARAM,
    CapabilitySig,
    Subject,
    VocabEntry,
    VocabKind,
    global_vocabulary,
)
from lorecraft.types import JsonObject

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext

log = logging.getLogger(__name__)

ConditionPredicate = Callable[[JsonObject, "GameContext"], bool]


class ConditionRegistry:
    """Registry of dialogue condition predicates.

    Built-in conditions (actor_has_flag, actor_lacks_flag) are registered
    at module load. New predicates can be registered without touching
    dialogue.py, enabling level checks, item checks, quest state, etc.
    """

    def __init__(self) -> None:
        self._predicates: dict[str, ConditionPredicate] = {}

    def register(self, condition_name: str, predicate: ConditionPredicate) -> None:
        """Register a condition predicate by name (no catalog descriptor)."""
        self._predicates[condition_name] = predicate

    def register_spec(self, spec: VocabEntry, predicate: ConditionPredicate) -> None:
        """Register a predicate *and* publish its descriptor to the shared catalog.

        See ``docs/scripting_engine_design.md`` §8. An exact-name collision in the shared
        catalog raises ``VocabularyError`` rather than silently overwriting.
        """
        global_vocabulary().register(spec)
        self._predicates[spec.name] = predicate

    def evaluate(self, conditions: JsonObject, ctx: "GameContext") -> bool:
        """Evaluate all conditions; all must pass (AND logic).

        Returns False if any condition fails or any registered predicate
        raises an exception. Unknown condition types are ignored (safe
        fallback for forward compatibility with new dialogue trees).
        """
        if not conditions:
            return True
        for condition_name, condition_data in conditions.items():
            if condition_name not in self._predicates:
                continue
            try:
                predicate = self._predicates[condition_name]
                if not predicate(condition_data, ctx):  # type: ignore[arg-type]
                    return False
            except Exception:
                # Degrade to "hidden" so a buggy predicate can't expose a
                # choice/exit it shouldn't — but log it, otherwise the option
                # silently vanishes from the dialogue with no way to diagnose.
                log.exception("dialogue_condition_failed condition=%s", condition_name)
                return False
        return True

    def __contains__(self, condition_name: str) -> bool:
        return condition_name in self._predicates


_registry = ConditionRegistry()


def _actor_has_flag(data: JsonObject, ctx: "GameContext") -> bool:
    """Check that all named flags are set on the actor."""
    for flag in data:  # type: ignore[union-attr]
        if not ctx.player.flags.get(str(flag)):
            return False
    return True


def _actor_lacks_flag(data: JsonObject, ctx: "GameContext") -> bool:
    """Check that none of the named flags are set on the actor."""
    for flag in data:  # type: ignore[union-attr]
        if ctx.player.flags.get(str(flag)):
            return False
    return True


# `actor_has_flag`/`actor_lacks_flag` are the §8.4 canonical names for the actor-flag
# capability, shared with command_conditions' identically-named predicates (same capability
# signature, two authoring surfaces — the catalog's idempotent same-capability registration
# makes that legal, exactly like `actor_reputation_at_least`). The dialogue surface accepts a
# list of flags (all must match); the command surface takes a single colon-string flag.
# The descriptor must be byte-identical to the command surface's (command_conditions.py) so the
# catalog's idempotent same-capability registration yields one import-order-independent entry.
_registry.register_spec(
    VocabEntry(
        name="actor_has_flag",
        kind=VocabKind.CONDITION,
        subject=Subject.ACTOR,
        category="flags",
        doc="The actor has the named flag(s) set.",
        capability=CapabilitySig(Subject.ACTOR, "flags", "<flag>", "has"),
        params=(FLAG_PARAM,),
    ),
    _actor_has_flag,
)
_registry.register_spec(
    VocabEntry(
        name="actor_lacks_flag",
        kind=VocabKind.CONDITION,
        subject=Subject.ACTOR,
        category="flags",
        doc="The actor does not have the named flag(s) set.",
        capability=CapabilitySig(Subject.ACTOR, "flags", "<flag>", "lacks"),
        params=(FLAG_PARAM,),
    ),
    _actor_lacks_flag,
)


def get_registry() -> ConditionRegistry:
    """Get the global dialogue condition registry."""
    return _registry
