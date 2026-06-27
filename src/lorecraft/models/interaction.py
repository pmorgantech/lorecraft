"""Player interaction table definitions."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class TradeOffer(SQLModel, table=True):
    id: str = Field(primary_key=True)
    initiator_id: str
    recipient_id: str
    initiator_items: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    recipient_items: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "pending"
    created_at: float
    expires_at: float


class PvpConsent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    player_a_id: str
    player_b_id: str
    consented_at: float
    revoked_at: float | None = None
