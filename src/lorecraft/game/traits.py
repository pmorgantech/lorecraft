"""Trait definitions and registry (engine_core.md §3.4, the "smaller surface" item).

Traits are semi-permanent modifier bundles (boons/banes) — distinct from
timed active effects. Tier 1 ships one TraitSource: active effects' own
grants_traits. Tier 2 adds equipment (grant_trait effect descriptors) and
innate traits (PlayerStats.traits). Registers itself as a Tier 1
ModifierSource too: traits contribute modifiers through the same resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlmodel import Session, select

from lorecraft.game import effects as effects_module
from lorecraft.game import modifiers as modifiers_module
from lorecraft.game.modifiers import Modifier
from lorecraft.models.meters import ActiveEffect


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


class ActiveEffectTraitSource:
    """TraitSource that contributes every active effect's granted traits.

    Registered as Tier 1's one built-in TraitSource — Tier 2 adds equipment
    and innate (PlayerStats.traits) sources.
    """

    def traits_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> set[str]:
        statement = select(ActiveEffect).where(
            ActiveEffect.entity_type == entity_type,
            ActiveEffect.entity_id == entity_id,
        )
        names: set[str] = set()
        for effect in session.exec(statement).all():
            effect_def = effects_module.get_registry().get(effect.effect_key)
            if effect_def is not None:
                names.update(effect_def.grants_traits(effect))
        return names


class TraitModifierSource:
    """ModifierSource that contributes every currently-held trait's modifiers.

    Registered with game/modifiers.py's ModifierRegistry at this module's
    import time — the Tier 1 "trait" source §3.5 calls for.
    """

    def modifiers_for(self, session: Session, entity_type: str, entity_id: str):
        modifiers: list[Modifier] = []
        for name in get_registry().traits_for(session, entity_type, entity_id):
            trait_def = get_registry().get(name)
            if trait_def is not None:
                modifiers.extend(trait_def.modifiers)
        return modifiers


_registry.register_source(ActiveEffectTraitSource())
modifiers_module.get_registry().register(TraitModifierSource())
