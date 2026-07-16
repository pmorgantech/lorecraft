"""Canonical body/equipment view model.

This is Tier 2 presentation policy for equipment and condition inspection. The
engine still only knows item locations and meters; body parts and how slots map
onto them belong to the equipment/combat feature layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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


def validate_body_slots() -> None:
    """Fail fast if the body view drifts from the physical slot registry."""
    missing = set(ALL_SLOTS) - set(BODY_SLOT_ORDER)
    extra = set(BODY_SLOT_ORDER) - set(ALL_SLOTS)
    if missing or extra:
        raise ValueError(f"body slot layout mismatch: missing={missing} extra={extra}")
