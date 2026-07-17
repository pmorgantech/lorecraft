"""Canonical body/equipment view model.

This is Tier 2 presentation policy for equipment inspection. The engine still
only knows item locations and meters; body parts and how slots map onto them
belong to the equipment feature layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

from sqlmodel import Session

from lorecraft.engine.models.items import ItemStack
from lorecraft.engine.models.world import Item
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.features.equipment.slots import ALL_SLOTS, slot_label
from lorecraft.types import JsonObject, JsonValue

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
        }
        for part in BODY_PARTS
    ]


def body_equipment_view(equipped: Sequence[tuple[ItemStack, Item]]) -> list[JsonObject]:
    view = empty_body_view()
    slots_by_name: dict[str, JsonObject] = {}
    for part in view:
        slots = part.get("slots")
        if not isinstance(slots, list):
            continue
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            slot_name = slot.get("slot")
            if isinstance(slot_name, str):
                slots_by_name[slot_name] = slot
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


def player_body_snapshot(session: Session, player_id: str) -> JsonObject:
    equipped = player_equipment(session, player_id)
    body = body_equipment_view(equipped)
    equipment: list[JsonValue] = [
        {
            "slot": stack.slot,
            "item_id": item.id,
            "name": item.name,
            "quantity": stack.quantity,
            "instance_id": stack.instance_id,
        }
        for stack, item in equipped
    ]
    return {
        "equipment": equipment,
        "body": cast(list[JsonValue], body),
    }


def player_body_view(session: Session, player_id: str) -> list[JsonObject]:
    snapshot = player_body_snapshot(session, player_id)
    body = snapshot.get("body")
    return cast(list[JsonObject], body) if isinstance(body, list) else empty_body_view()


def player_equipment(session: Session, player_id: str) -> list[tuple[ItemStack, Item]]:
    item_repo = ItemRepo(session)
    equipped: list[tuple[ItemStack, Item]] = []
    for stack in StackRepo(session).stacks_for_owner("player", player_id):
        if stack.slot is None:
            continue
        item = item_repo.get(stack.item_id)
        if item is not None:
            equipped.append((stack, item))
    return equipped


def validate_body_slots() -> None:
    """Fail fast if the body view drifts from the physical slot registry."""
    missing = set(ALL_SLOTS) - set(BODY_SLOT_ORDER)
    extra = set(BODY_SLOT_ORDER) - set(ALL_SLOTS)
    if missing or extra:
        raise ValueError(f"body slot layout mismatch: missing={missing} extra={extra}")
