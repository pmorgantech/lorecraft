"""Audit log table definitions."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class AuditEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    transaction_id: str = Field(index=True)
    correlation_id: str = Field(index=True)
    parent_transaction_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    actor_id: str = Field(index=True)
    event_type: str = Field(index=True)
    source_type: str
    target_id: str | None = None
    room_id: str = Field(index=True)
    game_time: float
    real_time: float = Field(index=True)
    severity: str = "INFO"
    summary: str
    payload_json: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
