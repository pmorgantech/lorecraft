"""Scheduled job table definitions."""

from __future__ import annotations

from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class ScheduledJob(SQLModel, table=True):
    """A durable scheduler entry, polled by `SchedulerService._on_time_advanced`.

    ``ix_scheduledjob_status_due_at_epoch`` is load-bearing, not a nice-to-have:
    ``dispatched``/``cancelled`` rows are never purged, so a live server's table
    grows without bound while the ``due()`` query's actual working set (pending
    rows) stays tiny. Without a composite index leading on ``status``, SQLite's
    only option is the single-column ``due_at_epoch`` index, which — because
    ``due_at_epoch`` never exceeds the ever-advancing current epoch — matches
    almost every historical row on every tick, then filters for ``status`` one
    row at a time. Column order matters: ``status`` (the equality predicate,
    low cardinality) leads, ``due_at_epoch`` (the range predicate) trails, so a
    tick seeks directly into the pending partition instead of scanning the
    whole table.
    """

    id: str = Field(primary_key=True)
    job_type: str = Field(index=True)
    due_at_epoch: float = Field(index=True)
    status: str = "pending"  # pending|dispatched|cancelled
    payload: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: float = 0.0

    __table_args__ = (
        Index("ix_scheduledjob_status_due_at_epoch", "status", "due_at_epoch"),
    )
