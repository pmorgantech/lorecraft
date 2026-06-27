"""Combat table definitions."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class CombatSession(SQLModel, table=True):
    id: str = Field(primary_key=True)
    room_id: str
    started_at: float
    status: str = "active"
    combatants: list[JsonObject] = Field(default_factory=list, sa_column=Column(JSON))
