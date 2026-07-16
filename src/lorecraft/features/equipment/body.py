"""Canonical body/equipment view model.

This is Tier 2 presentation policy for equipment and condition inspection. The
engine still only knows item locations and meters; body parts and how slots map
onto them belong to the equipment/combat feature layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import Literal

from lorecraft.engine.models.items import ItemStack
from lorecraft.engine.models.world import Item
from lorecraft.features.equipment.slots import ALL_SLOTS, slot_label
from lorecraft.types import JsonObject

BodyPartKey = Literal[
    "head",
    "neck_shoulders",
    "torso",
    "arms_hands",
    "hands",
    "waist",
    "legs_feet",
]


@dataclass(frozen=True)
class BodyPartDef:
    key: BodyPartKey
    label: str
    slots: tuple[str, ...]


BODY_PARTS: tuple[BodyPartDef, ...] = (
    BodyPartDef("head", "Head", ("head", "face")),
    BodyPartDef("neck_shoulders", "Neck & Shoulders", ("neck", "shoulders")),
    BodyPartDef("torso", "Torso", ("torso", "back")),
    BodyPartDef("arms_hands", "Arms & Hands", ("hands", "finger_l", "finger_r")),
    BodyPartDef("hands", "Held", ("main_hand", "off_hand")),
    BodyPartDef("waist", "Waist", ("waist",)),
    BodyPartDef("legs_feet", "Legs & Feet", ("legs", "feet")),
)

BODY_SLOT_ORDER: tuple[str, ...] = tuple(
    slot for part in BODY_PARTS for slot in part.slots
)


def body_part_for_slot(slot: str) -> BodyPartKey | None:
    for part in BODY_PARTS:
        if slot in part.slots:
            return part.key
    return None


def empty_body_view() -> list[JsonObject]:
    return [
        {
            "key": part.key,
            "label": part.label,
            "slots": [
                {
                    "slot": slot,
                    "label": slot_label(slot),
                    "item": None,
                }
                for slot in part.slots
            ],
            "wounds": [],
        }
        for part in BODY_PARTS
    ]


def body_equipment_view(equipped: Sequence[tuple[ItemStack, Item]]) -> list[JsonObject]:
    view = empty_body_view()
    slots_by_name = {
        slot["slot"]: slot
        for part in view
        for slot in part["slots"]
        if isinstance(slot, dict)
    }
    for stack, item in equipped:
        if stack.slot is None:
            continue
        slot = slots_by_name.get(stack.slot)
        if slot is None:
            continue
        slot["item"] = {
            "stack_id": stack.id,
            "item_id": item.id,
            "name": item.name,
            "description": item.description,
            "quantity": stack.quantity,
            "wearable": item.wearable,
            "slot": stack.slot,
        }
    return view


def validate_body_slots() -> None:
    """Fail fast if the body view drifts from the physical slot registry."""
    missing = set(ALL_SLOTS) - set(BODY_SLOT_ORDER)
    extra = set(BODY_SLOT_ORDER) - set(ALL_SLOTS)
    if missing or extra:
        raise ValueError(f"body slot layout mismatch: missing={missing} extra={extra}")
