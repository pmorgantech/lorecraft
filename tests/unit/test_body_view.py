"""Tests for the shared body/equipment view model."""

from __future__ import annotations

from lorecraft.features.equipment.body import (
    BODY_SLOT_ORDER,
    body_part_for_slot,
    body_equipment_view,
    empty_body_view,
    validate_body_slots,
)
from lorecraft.engine.models.items import ItemStack
from lorecraft.engine.models.world import Item
from lorecraft.features.equipment.slots import ALL_SLOTS


def test_body_slot_layout_covers_equipment_slots_once() -> None:
    validate_body_slots()
    assert set(BODY_SLOT_ORDER) == set(ALL_SLOTS)
    assert len(BODY_SLOT_ORDER) == len(set(BODY_SLOT_ORDER))


def test_empty_body_view_has_every_slot_empty() -> None:
    view = empty_body_view()
    slots = [slot for part in view for slot in part["slots"]]

    assert {slot["slot"] for slot in slots} == set(ALL_SLOTS)
    assert all(slot["item"] is None for slot in slots)
    assert body_part_for_slot("head") == "head"
    assert body_part_for_slot("main_hand") == "hands"
    assert body_part_for_slot("missing") is None


def test_body_equipment_view_populates_equipped_items() -> None:
    helmet = Item(
        id="helmet",
        name="Equippable Helmet",
        description="A test helm.",
        slot="head",
        wearable=True,
    )
    wrench = Item(
        id="wrench",
        name="Clockwork Wrench",
        description="A precise tool.",
        slot="main_hand",
    )
    view = body_equipment_view(
        [
            (
                ItemStack(
                    id=1,
                    item_id="helmet",
                    owner_type="player",
                    owner_id="player-1",
                    quantity=1,
                    slot="head",
                ),
                helmet,
            ),
            (
                ItemStack(
                    id=2,
                    item_id="wrench",
                    owner_type="player",
                    owner_id="player-1",
                    quantity=1,
                    slot="main_hand",
                ),
                wrench,
            ),
        ]
    )
    slots = {slot["slot"]: slot for part in view for slot in part["slots"]}

    assert slots["head"]["item"]["name"] == "Equippable Helmet"
    assert slots["main_hand"]["item"]["item_id"] == "wrench"
    assert slots["off_hand"]["item"] is None
