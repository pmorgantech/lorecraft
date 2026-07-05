"""Encumbrance: carry-capacity resolution and weight bands (docs/inventory_equipment.md §5).

Carry capacity is resolved, never stored (engine_core.md §3.5) — this module
composes the Tier 1 modifier resolver with the equipment carry_bonus source
(game/equipment_source.py). Total carried weight sums every stack the player
directly owns (loose + equipped); nested-container contents are not walked
recursively here — a future refinement once containers commonly nest.
"""

from __future__ import annotations

from typing import Literal

from sqlmodel import Session

from lorecraft.engine.game.modifiers import resolve_for
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.stack_repo import StackRepo

EncumbranceBand = Literal["unburdened", "burdened", "overloaded"]

BURDENED_MULTIPLIER = 1.0
OVERLOADED_MULTIPLIER = 1.5


def carry_base(strength: int) -> float:
    """Base carry capacity before modifiers."""
    return 40.0 + 4.0 * strength


def resolve_carry_capacity(session: Session, player_id: str, strength: int) -> float:
    return resolve_for(
        session, "player", player_id, "carry_capacity", base=carry_base(strength)
    )


def total_carried_weight(session: Session, player_id: str) -> float:
    """Sum of item.weight * quantity over every stack the player owns (any slot)."""
    stack_repo = StackRepo(session)
    item_repo = ItemRepo(session)
    total = 0.0
    for stack in stack_repo.stacks_for_owner("player", player_id):
        item = item_repo.get(stack.item_id)
        if item is not None:
            total += item.weight * stack.quantity
    return total


def encumbrance_band(total_weight: float, capacity: float) -> EncumbranceBand:
    if capacity <= 0:
        return "overloaded" if total_weight > 0 else "unburdened"
    if total_weight <= capacity * BURDENED_MULTIPLIER:
        return "unburdened"
    if total_weight <= capacity * OVERLOADED_MULTIPLIER:
        return "burdened"
    return "overloaded"
