"""Equipment ModifierSource + TraitSource (docs/inventory_equipment.md §9).

Walks a player's equipped (slot != None) stacks and compiles each item's
effects descriptors into Tier 1 modifiers/trait grants. Registers itself
with the Tier 1 modifier registry and Sprint 19's trait registry at import
time — imported for side effects from main.py, mirroring game/traits.py.
"""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.engine.game import modifiers as modifiers_module
from lorecraft.engine.game import traits as traits_module
from lorecraft.features.items.effects import compile_item_modifiers, item_granted_traits
from lorecraft.engine.game.modifiers import Modifier
from lorecraft.engine.models.items import ItemStack
from lorecraft.engine.models.world import Item
from lorecraft.engine.repos.item_repo import ItemRepo


def _equipped_items(session: Session, player_id: str) -> list[Item]:
    statement = select(ItemStack).where(
        ItemStack.owner_type == "player",
        ItemStack.owner_id == player_id,
        ItemStack.slot.is_not(None),  # type: ignore[attr-defined]
    )
    item_repo = ItemRepo(session)
    items = []
    for stack in session.exec(statement).all():
        item = item_repo.get(stack.item_id)
        if item is not None:
            items.append(item)
    return items


class EquipmentModifierSource:
    """ModifierSource contributing every equipped item's effects descriptors."""

    def modifiers_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> list[Modifier]:
        if entity_type != "player":
            return []
        modifiers: list[Modifier] = []
        for item in _equipped_items(session, entity_id):
            modifiers.extend(compile_item_modifiers(item))
        return modifiers


class EquipmentTraitSource:
    """TraitSource contributing every equipped item's grant_trait descriptors."""

    def traits_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> set[str]:
        if entity_type != "player":
            return set()
        names: set[str] = set()
        for item in _equipped_items(session, entity_id):
            names |= item_granted_traits(item)
        return names


_registered = False


def register() -> None:
    """Register the equipment modifier source + equipment trait source. Called
    by the `equipment` feature manifest when enabled (no longer a module-level
    import side effect). Idempotent (both sources are appended to lists, so a
    guard prevents double-registration)."""
    global _registered
    if _registered:
        return
    _registered = True
    modifiers_module.get_registry().register(EquipmentModifierSource())
    traits_module.get_registry().register_source(EquipmentTraitSource())
