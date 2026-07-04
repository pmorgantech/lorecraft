"""Bank table definitions (Sprint 28.3, docs/trade_economy.md §9).

A bank branch is an NPC marker, like a shop; banking commands only work in
a branch's room. Balance itself is a ledger holder
(CoinBalance("bank_account", account.id)) -- BankAccount is identity/
ownership only. One logical account, many branches: a player has exactly
one BankAccount, reachable from any branch.
"""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class Bank(SQLModel, table=True):
    id: str = Field(primary_key=True)
    npc_id: str = Field(foreign_key="npc.id", index=True, unique=True)
    name: str


class BankAccount(SQLModel, table=True):
    id: str = Field(primary_key=True)  # uuid4
    player_id: str = Field(foreign_key="player.id", unique=True, index=True)
