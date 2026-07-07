"""Mark boons: the mark→modifier bridge (Sprint 53.3).

Earned marks with boons contribute to the §3.5 modifier resolver through
`MarkBoonModifierSource`, the traits-feature `sources.py` pattern: a read-through
source over the player's `mark:<id>` flags and the in-memory mark registry —
no stored modifier state, recomputed per resolution. Registered idempotently
by the marks feature manifest.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session

from lorecraft.engine.game import modifiers as modifiers_module
from lorecraft.engine.game.modifiers import Modifier
from lorecraft.engine.models.player import Player
from lorecraft.features.marks.models import MarkRegistry, earned_flag, get_registry


class MarkBoonModifierSource:
    """ModifierSource contributing every earned mark's boons for a player."""

    def __init__(self, registry: MarkRegistry | None = None) -> None:
        self._registry = registry or get_registry()

    def modifiers_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> Iterable[Modifier]:
        if entity_type != "player":
            return []
        player = session.get(Player, entity_id)
        if player is None:
            return []
        modifiers: list[Modifier] = []
        for mark in self._registry.all():
            if not mark.boons or not player.flags.get(earned_flag(mark.id)):
                continue
            modifiers.extend(
                Modifier(
                    key=boon.key,
                    kind=boon.kind,
                    amount=boon.amount,
                    source=f"mark:{mark.id}",
                )
                for boon in mark.boons
            )
        return modifiers


_registered = False


def register() -> None:
    """Register the mark-boon modifier source. Called by the marks feature
    manifest when enabled. Idempotent: the modifier registry appends sources,
    so a guard prevents double-registration (see ModifierRegistry docstring).
    """
    global _registered
    if _registered:
        return
    _registered = True
    modifiers_module.get_registry().register(MarkBoonModifierSource())
