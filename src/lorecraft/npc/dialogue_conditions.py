"""Dialogue choice/exit condition registry: pluggable predicates for visibility."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from lorecraft.types import JsonObject

if TYPE_CHECKING:
    from lorecraft.game.context import GameContext

ConditionPredicate = Callable[[JsonObject, "GameContext"], bool]


class ConditionRegistry:
    """Registry of dialogue condition predicates.

    Built-in conditions (required_flags, forbidden_flags) are registered
    at module load. New predicates can be registered without touching
    dialogue.py, enabling level checks, item checks, quest state, etc.
    """

    def __init__(self) -> None:
        self._predicates: dict[str, ConditionPredicate] = {}

    def register(self, condition_name: str, predicate: ConditionPredicate) -> None:
        """Register a condition predicate by name."""
        self._predicates[condition_name] = predicate

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
                return False
        return True

    def __contains__(self, condition_name: str) -> bool:
        return condition_name in self._predicates


_registry = ConditionRegistry()


def _required_flags_satisfied(data: JsonObject, ctx: "GameContext") -> bool:
    """Check that all required flags are set."""
    for flag in data:  # type: ignore[union-attr]
        if not ctx.player.flags.get(str(flag)):
            return False
    return True


def _forbidden_flags_clear(data: JsonObject, ctx: "GameContext") -> bool:
    """Check that no forbidden flags are set."""
    for flag in data:  # type: ignore[union-attr]
        if ctx.player.flags.get(str(flag)):
            return False
    return True


_registry.register("required_flags", _required_flags_satisfied)
_registry.register("forbidden_flags", _forbidden_flags_clear)


def get_registry() -> ConditionRegistry:
    """Get the global dialogue condition registry."""
    return _registry
