"""Scheduled job table definitions."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class ScheduledJob(SQLModel, table=True):
    id: str = Field(primary_key=True)
    job_type: str = Field(index=True)
    due_at_epoch: float = Field(index=True)
    status: str = "pending"  # pending|dispatched|cancelled
    payload: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: float = 0.0
