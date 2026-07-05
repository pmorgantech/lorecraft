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
    status: str = "active"  # active | completed | failed
    started_at: float
    completed_at: float | None = None
    # Game-clock epoch (WorldClock.game_epoch) the current stage became
    # active, in the same units as scheduler/mobile-route `_ticks` fields.
    # Backs Sprint 30.2's QuestTimerService timeout sweep; None for stages
    # entered before this field existed (never times out).
    stage_started_epoch: float | None = None
