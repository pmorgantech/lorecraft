"""Standard item components: durability, openable, lit, container, mechanism.

Tier 2 registration on top of Sprint 16's ComponentRegistry (engine_core.md
§3.1). Registers itself at import time — imported for side effects (like
game/traits.py) from main.py's lifespan. See docs/inventory_equipment.md §7
and docs/roadmap.md Sprint 30.2 for "mechanism" (levers/dials puzzles).
"""

from __future__ import annotations

from lorecraft.engine.game.components import ComponentDef, get_registry
from lorecraft.engine.models.world import Item
from lorecraft.types import JsonValue


def _durability_applies(item: Item) -> bool:
    return item.max_durability is not None


def _durability_initial(item: Item) -> JsonValue:
    return {"current": item.max_durability}


def _durability_validate(state: JsonValue) -> list[str]:
    if not isinstance(state, dict) or "current" not in state:
        return ["durability state must be a dict with a 'current' key"]
    current = state["current"]
    if (
        not isinstance(current, (int, float))
        or isinstance(current, bool)
        or current < 0
    ):
        return ["durability 'current' must be a non-negative number"]
    return []


def _openable_applies(item: Item) -> bool:
    return item.capacity is not None


def _openable_initial(item: Item) -> JsonValue:
    del item
    return {"open": False}


def _openable_validate(state: JsonValue) -> list[str]:
    if not isinstance(state, dict) or "open" not in state:
        return ["openable state must be a dict with an 'open' key"]
    if not isinstance(state["open"], bool):
        return ["openable 'open' must be a boolean"]
    return []


def _lit_applies(item: Item) -> bool:
    return item.light > 0


def _lit_initial(item: Item) -> JsonValue:
    del item
    return {"lit": False}


def _lit_validate(state: JsonValue) -> list[str]:
    if not isinstance(state, dict) or "lit" not in state:
        return ["lit state must be a dict with a 'lit' key"]
    if not isinstance(state["lit"], bool):
        return ["lit 'lit' must be a boolean"]
    return []


def _container_applies(item: Item) -> bool:
    return item.capacity is not None


def _container_initial(item: Item) -> JsonValue:
    del item
    return {}


def _container_validate(state: JsonValue) -> list[str]:
    del state
    return []


def _mechanism_applies(item: Item) -> bool:
    return len(item.mechanism_states) > 0


def _mechanism_initial(item: Item) -> JsonValue:
    del item
    return {"index": 0}


def _mechanism_validate(state: JsonValue) -> list[str]:
    if not isinstance(state, dict) or "index" not in state:
        return ["mechanism state must be a dict with an 'index' key"]
    index = state["index"]
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        return ["mechanism 'index' must be a non-negative integer"]
    return []


def register() -> None:
    """Register the standard item component defs (durability, openable, lit,
    container, mechanism) on the shared component registry. Called by the
    `item_components` feature manifest when enabled (no longer a module-level
    import side effect). Idempotent."""
    get_registry().register(
        ComponentDef(
            name="durability",
            applies_to=_durability_applies,
            initial_state=_durability_initial,
            validate=_durability_validate,
        )
    )
    get_registry().register(
        ComponentDef(
            name="openable",
            applies_to=_openable_applies,
            initial_state=_openable_initial,
            validate=_openable_validate,
        )
    )
    get_registry().register(
        ComponentDef(
            name="lit",
            applies_to=_lit_applies,
            initial_state=_lit_initial,
            validate=_lit_validate,
        )
    )
    get_registry().register(
        ComponentDef(
            name="container",
            applies_to=_container_applies,
            initial_state=_container_initial,
            validate=_container_validate,
        )
    )
    get_registry().register(
        ComponentDef(
            name="mechanism",
            applies_to=_mechanism_applies,
            initial_state=_mechanism_initial,
            validate=_mechanism_validate,
        )
    )
