"""Admin user table definition."""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class AdminUser(SQLModel, table=True):
    id: str = Field(primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    role: str  # observer|moderator|world-builder|superadmin
    created_at: float
    revoked_at: float | None = None
