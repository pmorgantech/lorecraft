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


class CrashReport(SQLModel, table=True):
    """An unhandled exception from either command entry point (Sprint 57.3).

    Distinct from `AuditEvent`'s `COMMAND_FAILED`-style rows: those cover
    *expected* failures a handler reports on purpose (a blocked command, a
    rule violation); this covers the command pipeline itself blowing up —
    a bug, not a game-rule outcome — captured with enough to reproduce it
    (`command_text`, full `stack_trace`) without grepping server logs.
    """

    id: int | None = Field(default=None, primary_key=True)
    transaction_id: str = Field(index=True)
    correlation_id: str = Field(index=True)
    player_id: str = Field(index=True)
    command_text: str
    stack_trace: str
    real_time: float = Field(index=True)
