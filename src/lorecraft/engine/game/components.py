"""Item component registry and definitions.

Components are registered, pluggable attributes of ItemInstances that persist state.
Tier 1 (engine core) defines the registry only; Tier 2 (standard modules) registers
durability, openable, lit, container, and other components.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from lorecraft.engine.models.world import Item
from lorecraft.types import JsonValue


@dataclass(frozen=True)
class ComponentDef:
    """Definition of a registerable component type.

    Args:
        name: Unique component identifier (e.g., "durability", "openable").
        applies_to: Predicate to determine if an item can have this component.
        initial_state: Factory function to generate initial state for a fresh instance.
        validate: Lint function to check state validity; returns list of error messages.
    """

    name: str
    applies_to: Callable[[Item], bool]
    initial_state: Callable[[Item], JsonValue]
    validate: Callable[[JsonValue], list[str]]


class ComponentRegistry:
    """Registry for item component definitions.

    Used during instance spawning (applies_to check) and content validation.
    """

    def __init__(self) -> None:
        self._components: dict[str, ComponentDef] = {}

    def register(self, component: ComponentDef) -> None:
        """Register a component definition (overwrites any existing registration by name)."""
        self._components[component.name] = component

    def components_for(self, item: Item) -> list[ComponentDef]:
        """Get all components that apply to an item.

        Args:
            item: The Item to query.

        Returns:
            List of ComponentDef instances that apply to this item.
        """
        return [c for c in self._components.values() if c.applies_to(item)]

    def requires_instance(self, item: Item) -> bool:
        """Check if an item requires instantiation (has any component).

        Args:
            item: The Item to query.

        Returns:
            True if the item has at least one component.
        """
        return len(self.components_for(item)) > 0

    def __contains__(self, name: str) -> bool:
        """Check if a component name is registered."""
        return name in self._components

    def get(self, name: str) -> ComponentDef | None:
        """Get a component definition by name.

        Args:
            name: Component name to look up.

        Returns:
            ComponentDef if found, None otherwise.
        """
        return self._components.get(name)


_registry = ComponentRegistry()


def get_registry() -> ComponentRegistry:
    """Get the global component registry."""
    return _registry
