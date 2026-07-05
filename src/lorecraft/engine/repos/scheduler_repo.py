"""Scheduled job data access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, select

from lorecraft.models.scheduler import ScheduledJob
from lorecraft.engine.repos.base import Repository


class SchedulerRepo(Repository[ScheduledJob, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ScheduledJob)

    def due(self, current_epoch: float) -> Sequence[ScheduledJob]:
        statement = select(ScheduledJob).where(
            ScheduledJob.status == "pending",
            ScheduledJob.due_at_epoch <= current_epoch,
        )
        return self.session.exec(statement).all()
