"""Quest table definitions."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class Quest(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str
    description: str
    stages: list[JsonObject] = Field(default_factory=list, sa_column=Column(JSON))


class PlayerQuestProgress(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    player_id: str = Field(index=True)
    quest_id: str
    current_stage_id: str
    status: str = "active"
    started_at: float
    completed_at: float | None = None
