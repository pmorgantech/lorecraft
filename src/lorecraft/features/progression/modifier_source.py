"""Skill-tree passive-ability bridge (Sprint 74.4, flavor B).

Every unlocked node carrying a `modifier` block contributes it to the Tier 1
`engine.game.modifiers` resolver — the same read-through pattern as
`marks/boons.py` and `traits/sources.py`. State-free: it reads the player's
`PlayerStats.unlocked_nodes` live, so a newly-trained passive applies
retroactively on the next resolution with no cache to invalidate (74-OI-4).

Which node grants which modifier is Tier 2 policy (the skill-tree YAML); this
source is a generic pump that plugs feature opinion into the engine hook — no
node ids or ability names are hardcoded here.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session

from lorecraft.engine.game import modifiers as modifiers_module
from lorecraft.engine.game.modifiers import Modifier
from lorecraft.engine.models.player import PlayerStats
from lorecraft.features.progression.skill_tree import (
    SkillTreeRegistry,
    get_registry,
)


class SkillTreeModifierSource:
    """ModifierSource contributing each unlocked node's passive `modifier`."""

    def __init__(self, registry: SkillTreeRegistry | None = None) -> None:
        self._registry = registry or get_registry()

    def modifiers_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> Iterable[Modifier]:
        if entity_type != "player":
            return []
        stats = session.get(PlayerStats, entity_id)
        if stats is None:
            return []
        modifiers: list[Modifier] = []
        for node_id in stats.unlocked_nodes:
            node = self._registry.get(node_id)
            if node is None or node.unlock.modifier is None:
                continue
            spec = node.unlock.modifier
            modifiers.append(
                Modifier(
                    key=spec.key,
                    kind=spec.kind,
                    amount=spec.amount,
                    source=f"ability:{node_id}",
                )
            )
        return modifiers


_registered = False


def register() -> None:
    """Register the skill-tree modifier source. Called by the progression feature
    manifest when enabled. Idempotent: the modifier registry appends sources, so
    a guard prevents double-registration (see ModifierRegistry docstring)."""
    global _registered
    if _registered:
        return
    _registered = True
    modifiers_module.get_registry().register(SkillTreeModifierSource())
