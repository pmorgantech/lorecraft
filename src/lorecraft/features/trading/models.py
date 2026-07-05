"""Player interaction table definitions."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class TradeOffer(SQLModel, table=True):
    """A pending player-to-player trade (Sprint 28.4, docs/trade_economy.md §8).

    Either side can add pledges (coins and/or carried stacks) via repeated
    `offer` calls; `accept` composes one `LedgerService.execute_exchange`
    with both directions as legs -- leg validation at that point *is* the
    escrow revalidation (if a pledged stack/coin balance is gone, the whole
    exchange raises and nothing moves).
    """

    id: str = Field(primary_key=True)  # uuid4
    initiator_id: str
    recipient_id: str
    initiator_coins: int = 0
    recipient_coins: int = 0
    # [stack_id, quantity] pairs pledged by each side.
    initiator_stacks: list[list[int]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    recipient_stacks: list[list[int]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    status: str = "pending"  # pending|accepted|declined|expired
    created_at: float
    expires_at: float


class PvpConsent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    player_a_id: str
    player_b_id: str
    consented_at: float
    revoked_at: float | None = None
