"""Trait registry (engine_core.md §3.4, the "smaller surface" item) — Tier 1.

Traits are semi-permanent modifier bundles (boons/banes) — distinct from
timed active effects. This module owns only the Tier 1 primitives: the
``TraitDef`` type, the ``TraitSource`` protocol, and the global
``TraitRegistry``. The concrete trait *sources* (active-effect grants, the
trait→modifier bridge) and the shipped standard trait defs are Tier 2 and
live in ``lorecraft.features.traits``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlmodel import Session

from lorecraft.engine.game.modifiers import Modifier


@dataclass(frozen=True)
class TraitDef:
    """Definition of a registerable trait (named boon/bane modifier-bundle)."""

    name: str
    modifiers: list[Modifier]
    description: str


class TraitSource(Protocol):
    """A pluggable contributor of trait names for a given entity."""

    def traits_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> set[str]: ...


class TraitRegistry:
    """Registry of trait definitions (keyed, overwrites on re-register) plus
    the sources that determine which traits an entity currently has."""

    def __init__(self) -> None:
        self._defs: dict[str, TraitDef] = {}
        self._sources: list[TraitSource] = []

    def register(self, trait_def: TraitDef) -> None:
        self._defs[trait_def.name] = trait_def

    def register_source(self, source: TraitSource) -> None:
        self._sources.append(source)

    def get(self, name: str) -> TraitDef | None:
        return self._defs.get(name)

    def traits_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> set[str]:
        """Every trait name granted to this entity, from all registered sources."""
        names: set[str] = set()
        for source in self._sources:
            names |= source.traits_for(session, entity_type, entity_id)
        return names


_registry = TraitRegistry()


def get_registry() -> TraitRegistry:
    """Get the global trait registry."""
    return _registry
