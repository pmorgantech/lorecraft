"""Canonical body/equipment view model.

This is Tier 2 presentation policy for equipment and condition inspection. The
engine still only knows item locations and meters; body parts and how slots map
onto them belong to the equipment/combat feature layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

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


def body_part_for_wound_location(location: str) -> BodyPartKey | None:
    if location == "head":
        return "head"
    if location == "torso":
        return "torso"
    if location in {"left_arm", "right_arm"}:
        return "arms_hands"
    if location in {"left_leg", "right_leg"}:
        return "legs_feet"
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


def add_wounds_to_body_view(view: list[JsonObject], wounds: Sequence[Any]) -> None:
    parts_by_key = {part["key"]: part for part in view}
    for wound in wounds:
        location = str(getattr(wound, "body_location", ""))
        part_key = body_part_for_wound_location(location)
        if part_key is None:
            continue
        part = parts_by_key.get(part_key)
        if part is None:
            continue
        wounds_list = part.get("wounds")
        if not isinstance(wounds_list, list):
            continue
        wounds_list.append(
            {
                "id": getattr(wound, "id", None),
                "body_location": location,
                "severity": getattr(wound, "severity", ""),
                "damage": getattr(wound, "damage", 0.0),
                "status": getattr(wound, "status", ""),
                "created_at_game_time": getattr(wound, "created_at_game_time", None),
                "healed_at_game_time": getattr(wound, "healed_at_game_time", None),
            }
        )


def validate_body_slots() -> None:
    """Fail fast if the body view drifts from the physical slot registry."""
    missing = set(ALL_SLOTS) - set(BODY_SLOT_ORDER)
    extra = set(BODY_SLOT_ORDER) - set(ALL_SLOTS)
    if missing or extra:
        raise ValueError(f"body slot layout mismatch: missing={missing} extra={extra}")
