"""Equipment slot data (docs/inventory_equipment.md §4).

Slots are data, not hardcoded branches — a world can extend this set without
engine edits (this module is the shipped default; nothing here is Tier 1).
"""

from __future__ import annotations

WORN_SLOTS = frozenset(
    {
        "head",
        "face",
        "neck",
        "shoulders",
        "torso",
        "back",
        "hands",
        "finger_l",
        "finger_r",
        "waist",
        "legs",
        "feet",
    }
)
WIELD_SLOTS = frozenset({"main_hand", "off_hand"})
ALL_SLOTS = WORN_SLOTS | WIELD_SLOTS
FINGER_SLOTS = ("finger_l", "finger_r")

# "finger" is a generic definitional slot on the Item — the wear command picks
# whichever physical finger_l/finger_r slot is free (rings are interchangeable).
GENERIC_SLOT_ALIASES = {"finger": FINGER_SLOTS}


def slot_label(slot: str | None) -> str:
    """Human-readable slot name for equipment listings/messages."""
    if slot is None:
        return "loose"
    return slot.replace("_", " ")


def is_valid_physical_slot(slot: str) -> bool:
    return slot in ALL_SLOTS


def item_fits_slot(item_slot: str | None, physical_slot: str) -> bool:
    """Whether an Item.slot definition matches a physical wear location.

    Direct match, or the item's generic "finger" slot matching either
    physical finger_l/finger_r location.
    """
    if item_slot is None:
        return False
    if item_slot == physical_slot:
        return True
    aliased = GENERIC_SLOT_ALIASES.get(item_slot)
    return aliased is not None and physical_slot in aliased
