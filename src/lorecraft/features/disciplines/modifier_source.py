"""Passive-ability modifier bridge (Sprint 78.6, ported from progression 74.4).

Every unlocked ability carrying a `modifier` block contributes it to the Tier 1
`engine.game.modifiers` resolver — the same read-through pattern as
`marks/boons.py` and `traits/sources.py`. State-free: it reads the player's
`PlayerStats.unlocked_nodes` live, so a newly-trained passive applies
retroactively on the next resolution with no cache to invalidate.

Which ability grants which modifier is Tier 2 policy (`abilities.yaml`); this
source is a generic pump plugging feature opinion into the engine hook — no
ability ids or modifier keys are hardcoded here. The modifier `key` is whatever
the ability authored (e.g. `carry_capacity`, `price.buy`, `skill.perception`).
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session

from lorecraft.engine.game import modifiers as modifiers_module
from lorecraft.engine.game.modifiers import Modifier
from lorecraft.engine.models.player import PlayerStats
from lorecraft.features.disciplines.abilities import (
    AbilityRegistry,
    get_ability_registry,
)


class AbilityModifierSource:
    """ModifierSource contributing each unlocked ability's passive `modifier`."""

    def __init__(self, registry: AbilityRegistry | None = None) -> None:
        self._registry = registry or get_ability_registry()

    def modifiers_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> Iterable[Modifier]:
        if entity_type != "player":
            return []
        stats = session.get(PlayerStats, entity_id)
        if stats is None:
            return []
        modifiers: list[Modifier] = []
        for ability_id in stats.unlocked_nodes:
            record = self._registry.get(ability_id)
            if record is None or record.unlock.modifier is None:
                continue
            spec = record.unlock.modifier
            modifiers.append(
                Modifier(
                    key=spec.key,
                    kind=spec.kind,
                    amount=spec.amount,
                    source=f"ability:{ability_id}",
                )
            )
        return modifiers


_registered = False


def register() -> None:
    """Register the ability modifier source. Called by the disciplines feature
    manifest when enabled. Idempotent: the modifier registry appends sources, so
    a guard prevents double-registration (see ModifierRegistry docstring)."""
    global _registered
    if _registered:
        return
    _registered = True
    modifiers_module.get_registry().register(AbilityModifierSource())
