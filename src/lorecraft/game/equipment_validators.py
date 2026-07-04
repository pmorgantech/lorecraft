"""Player-holder move validator enforcing equip-slot mechanics.

Registers with Sprint 16's HolderRegistry (docs/inventory_equipment.md §4).
Fires on every move into a "player" holder; a `slot is not None` destination
is an equip attempt (slot must be known, the item must fit it, and the slot
must be empty — swap-by-move-out is the wear command's job, not this
validator's). A `slot is None` destination (loose carry) is untouched here;
carry-capacity overload is checked at the command layer (services/inventory.py),
which has visibility into whether weight is genuinely increasing.
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.errors import ConflictError, ValidationError
from lorecraft.game.equipment_slots import (
    WIELD_SLOTS,
    WORN_SLOTS,
    is_valid_physical_slot,
    item_fits_slot,
)
from lorecraft.game.holders import Location, get_registry as get_holder_registry
from lorecraft.models.world import Item
from lorecraft.repos.stack_repo import StackRepo


def _validate_player_equip(
    session: Session, dest: Location, item: object, quantity: int
) -> None:
    del quantity
    if dest.slot is None:
        return
    assert isinstance(item, Item)

    slot = dest.slot
    if not is_valid_physical_slot(slot):
        raise ValidationError(
            f"Unknown equipment slot '{slot}'", "validation_unknown_slot"
        )

    if not item_fits_slot(item.slot, slot):
        raise ValidationError(
            f"{item.name} can't go in the {slot.replace('_', ' ')} slot",
            "validation_slot_mismatch",
        )

    if slot in WORN_SLOTS and not item.wearable:
        raise ValidationError(f"{item.name} isn't wearable", "validation_not_wearable")
    if slot in WIELD_SLOTS and item.wearable:
        raise ValidationError(
            f"{item.name} can't be wielded", "validation_not_wieldable"
        )

    stack_repo = StackRepo(session)
    existing = stack_repo.stacks_at(Location("player", dest.owner_id, slot=slot))
    if existing:
        raise ConflictError(
            f"Slot '{slot}' is already occupied", "conflict_slot_occupied"
        )


_registered = False


def register() -> None:
    """Register the player equip-slot move validator on the holder registry.
    Called by the `equipment` feature manifest when enabled (no longer a
    module-level import side effect). Idempotent (move validators are appended
    per holder type, so a guard prevents double-registration)."""
    global _registered
    if _registered:
        return
    _registered = True
    get_holder_registry().register_move_validator("player", _validate_player_equip)
