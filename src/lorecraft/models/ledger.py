"""Coin balance table definition (engine_core.md §3.7)."""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class CoinBalance(SQLModel, table=True):
    """A coin balance as an attribute of any registered holder.

    Uses the SAME holder registry as ItemStack (game/holders.py) — a corpse
    holds coins with zero special-casing (holder_type="container"), a bank
    account is CoinBalance("bank_account", account_id) once Tier 2 registers
    that holder type. There is deliberately no Player.coins column.

    Invariants (enforced in code, not DB constraints — same posture as
    ItemStack's quantity floor):
    - balance >= 0 always.
    - At most one row per (holder_type, holder_id); rows are created lazily
      at first credit().
    """

    id: int | None = Field(default=None, primary_key=True)
    holder_type: str = Field(index=True)
    holder_id: str = Field(index=True)
    balance: int = 0
