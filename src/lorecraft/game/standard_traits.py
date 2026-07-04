"""Standard trait definitions + the innate (background/earned) trait source.

Sprint 24.1: equipment traits already register in game/equipment_source.py
(Sprint 23.2); this module adds the other leg — traits granted permanently
via PlayerStats.traits (character background, quest rewards, achievements)
— plus a small illustrative boon/bane set. Self-registers at import time,
imported for side effects from main.py.
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.game import traits as traits_module
from lorecraft.game.modifiers import Modifier
from lorecraft.game.traits import TraitDef
from lorecraft.models.player import PlayerStats

STANDARD_TRAITS = [
    TraitDef(
        name="keen_eyed",
        modifiers=[
            Modifier(
                key="skill.perception", kind="add", amount=10, source="trait:keen_eyed"
            )
        ],
        description="Sharp-sighted — better at spotting hidden things.",
    ),
    TraitDef(
        name="silver_tongued",
        modifiers=[
            Modifier(
                key="skill.persuasion",
                kind="add",
                amount=10,
                source="trait:silver_tongued",
            )
        ],
        description="Naturally persuasive in conversation.",
    ),
    TraitDef(
        name="sure_footed",
        modifiers=[
            Modifier(
                key="skill.survival", kind="add", amount=10, source="trait:sure_footed"
            )
        ],
        description="Rarely stumbles on rough terrain.",
    ),
    TraitDef(
        name="clumsy",
        modifiers=[
            Modifier(key="stat.agility", kind="add", amount=-2, source="trait:clumsy")
        ],
        description="A bit accident-prone.",
    ),
    TraitDef(
        name="frail",
        modifiers=[
            Modifier(key="stat.vitality", kind="add", amount=-2, source="trait:frail")
        ],
        description="Physically delicate.",
    ),
]

for _trait_def in STANDARD_TRAITS:
    traits_module.get_registry().register(_trait_def)


class InnateTraitSource:
    """TraitSource contributing PlayerStats.traits — background/earned traits
    that persist regardless of equipment or active effects."""

    def traits_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> set[str]:
        if entity_type != "player":
            return set()
        stats = session.get(PlayerStats, entity_id)
        if stats is None:
            return set()
        return set(stats.traits)


traits_module.get_registry().register_source(InnateTraitSource())
