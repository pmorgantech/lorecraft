"""Item stack and instance table definitions for unified item location model."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class ItemInstance(SQLModel, table=True):
    """Per-instance state for items with registered components.

    An instance carries identity and mutable component state; its location
    lives on the ItemStack row that references it (via unique FK).

    Invariant: exactly one ItemStack has instance_id = this.id (the unique FK).
    """

    id: str = Field(primary_key=True)  # uuid4
    item_id: str = Field(foreign_key="item.id", index=True)
    state: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    # state keyed by component name: {"durability": {"current": 480}, "openable": {"is_open": true}}


class ItemStack(SQLModel, table=True):
    """Unified item location and quantity model, replacing Player.inventory and RoomItem.

    Invariants:
    - quantity >= 1 (zero-quantity stacks are deleted, never stored)
    - instance_id IS NOT NULL ⇒ quantity == 1 (instanced items never stack)
    - at most one stack per (owner_type, owner_id, slot, item_id) with instance_id IS NULL
      (fungible stacks auto-merge; instanced stacks never merge)
    - An ItemInstance is referenced by exactly one stack (unique FK, enforced by DB)
    - A container may not contain itself, directly or transitively
    """

    id: int | None = Field(default=None, primary_key=True)
    item_id: str = Field(foreign_key="item.id", index=True)
    owner_type: str = Field(
        index=True
    )  # "player" | "room" | "container" | ... (registered)
    owner_id: str = Field(index=True)
    slot: str | None = (
        None  # sub-position within holder (e.g., equipment slot); None = loose
    )
    quantity: int = 1  # CHECK (quantity > 0) enforced in code
    instance_id: str | None = Field(
        default=None, foreign_key="iteminstance.id", unique=True
    )  # unique ensures 1:1 mapping; None = fungible stack
