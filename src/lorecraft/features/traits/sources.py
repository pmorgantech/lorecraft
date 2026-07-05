"""Tier 2 trait sources: the active-effect trait source and the trait→modifier
bridge, plus their registration.

The trait *registry* itself (``lorecraft.engine.game.traits``) is a Tier 1
primitive and always available; these sources are what make traits actually
contribute — active effects' ``grants_traits`` and each held trait's modifiers
— and are gated behind the `traits` feature.
"""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.engine.game import effects as effects_module
from lorecraft.engine.game import modifiers as modifiers_module
from lorecraft.engine.game.modifiers import Modifier
from lorecraft.engine.game.traits import get_registry
from lorecraft.engine.models.meters import ActiveEffect


class ActiveEffectTraitSource:
    """TraitSource that contributes every active effect's granted traits."""

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
    """ModifierSource that contributes every currently-held trait's modifiers —
    the "trait" modifier source (engine_core.md §3.5)."""

    def modifiers_for(self, session: Session, entity_type: str, entity_id: str):
        modifiers: list[Modifier] = []
        for name in get_registry().traits_for(session, entity_type, entity_id):
            trait_def = get_registry().get(name)
            if trait_def is not None:
                modifiers.extend(trait_def.modifiers)
        return modifiers


_registered = False


def register() -> None:
    """Register the trait system's sources (active-effect trait source + trait
    modifier source). Called by the `traits` feature manifest when enabled.
    Idempotent: these sources are appended to lists, so a guard prevents
    double-registration.
    """
    global _registered
    if _registered:
        return
    _registered = True
    get_registry().register_source(ActiveEffectTraitSource())
    modifiers_module.get_registry().register(TraitModifierSource())
