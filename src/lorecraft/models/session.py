"""Player session table definitions."""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class PlayerSession(SQLModel, table=True):
    id: str = Field(primary_key=True)
    player_id: str = Field(index=True)
    connected_at: float
    disconnected_at: float | None = None
    grace_expires_at: float | None = None
    status: str = "active"
