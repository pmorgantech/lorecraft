"""Quest stage/branch condition registry: pluggable predicates (Sprint 30.1).

Mirrors npc/dialogue_conditions.py's ConditionRegistry, but evaluates the
quest-authoring shape -- a list of `{"type": ..., ...}` dicts -- rather than
a dialogue choice's `{condition_name: data}` dict. Built-ins (flag_set,
flag_clear, room_visited, item_in_inventory) are registered at import time;
new predicates (e.g. npc_memory_conditions.py's "npc_remembers") register
without touching services/quest.py.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from lorecraft.game.holders import Location
from lorecraft.types import JsonObject

if TYPE_CHECKING:
    from lorecraft.game.context import GameContext

QuestConditionPredicate = Callable[[JsonObject, "GameContext"], bool]


class QuestConditionRegistry:
    """Registry of quest condition predicates, keyed by the condition's `type`."""

    def __init__(self) -> None:
        self._predicates: dict[str, QuestConditionPredicate] = {}

    def register(self, condition_type: str, predicate: QuestConditionPredicate) -> None:
        self._predicates[condition_type] = predicate

    def evaluate_all(self, conditions: list[JsonObject], ctx: "GameContext") -> bool:
        """All conditions must pass (AND). Unknown types are ignored -- forward
        compatible with quest content written for a predicate not yet
        registered in this build."""
        for cond in conditions:
            ctype = str(cond.get("type", ""))
            predicate = self._predicates.get(ctype)
            if predicate is not None and not predicate(cond, ctx):
                return False
        return True

    def __contains__(self, condition_type: str) -> bool:
        return condition_type in self._predicates


_registry = QuestConditionRegistry()


def _flag_set(cond: JsonObject, ctx: "GameContext") -> bool:
    return bool(ctx.player.flags.get(str(cond.get("flag"))))


def _flag_clear(cond: JsonObject, ctx: "GameContext") -> bool:
    return not ctx.player.flags.get(str(cond.get("flag")))


def _room_visited(cond: JsonObject, ctx: "GameContext") -> bool:
    return str(cond.get("room_id")) in ctx.player.visited_rooms


def _item_in_inventory(cond: JsonObject, ctx: "GameContext") -> bool:
    loc = Location("player", ctx.player.id)
    return ctx.stack_repo.quantity_of(loc, str(cond.get("item_id"))) > 0


_registry.register("flag_set", _flag_set)
_registry.register("flag_clear", _flag_clear)
_registry.register("room_visited", _room_visited)
_registry.register("item_in_inventory", _item_in_inventory)


def get_registry() -> QuestConditionRegistry:
    """Get the global quest condition registry."""
    return _registry
