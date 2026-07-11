"""Vendor shop table definitions (Sprint 28.1, docs/trade_economy.md §4).

A shop is data attached to an NPC; the shop's cash and its stock are two
separate concerns. Money is a ledger holder (CoinBalance("shop", shop.id));
`ShopStock` is listing state only — items materialize as `ItemStack`s (Sprint
16) only when actually bought, never held loose by the shop ahead of time.
"""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class Shop(SQLModel, table=True):
    id: str = Field(primary_key=True)
    npc_id: str = Field(foreign_key="npc.id", index=True, unique=True)
    name: str
    buys_categories: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    sell_ratio: float = 0.5
    # A per-shop adjustment ON TOP of its area's RegionPricing.region_mult
    # (Sprint 28.2) -- effective region_mult = area default * this. Defaults
    # to 1.0 (no shop-specific adjustment).
    region_mult: float = 1.0


class ShopStock(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(foreign_key="shop.id", index=True)
    item_id: str = Field(foreign_key="item.id")
    quantity: int = 0  # -1 = unlimited
    restock_to: int = 0
    restock_every_ticks: int = 0
    # Runtime-only counter (not authored) driving services/restock.py's sweep.
    ticks_since_restock: int = 0


class RegionPricing(SQLModel, table=True):
    """Per-zone price multiplier + per-good bias (Sprint 28.2, trade_economy.md §5).

    Keyed on ``Room.zone`` since Sprint 71.2 (the old ``area_id`` split).
    """

    zone: str = Field(primary_key=True)
    region_mult: float = 1.0
    bias: JsonObject = Field(
        default_factory=dict, sa_column=Column(JSON)
    )  # item_id -> mult
