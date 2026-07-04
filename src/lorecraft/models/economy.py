"""Vendor shop table definitions (Sprint 28.1, docs/trade_economy.md §4).

A shop is data attached to an NPC; the shop's cash and its stock are two
separate concerns. Money is a ledger holder (CoinBalance("shop", shop.id));
`ShopStock` is listing state only — items materialize as `ItemStack`s (Sprint
16) only when actually bought, never held loose by the shop ahead of time.
"""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class Shop(SQLModel, table=True):
    id: str = Field(primary_key=True)
    npc_id: str = Field(foreign_key="npc.id", index=True, unique=True)
    name: str
    buys_categories: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    sell_ratio: float = 0.5
    region_mult: float = 1.0


class ShopStock(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(foreign_key="shop.id", index=True)
    item_id: str = Field(foreign_key="item.id")
    quantity: int = 0  # -1 = unlimited
    restock_to: int = 0
    restock_every_ticks: int = 0
