"""Audit log data access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, col, select

from lorecraft.models.audit import AuditEvent
from lorecraft.repos.base import Repository


class AuditRepo(Repository[AuditEvent, int]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AuditEvent)

    def record(self, event: AuditEvent) -> AuditEvent:
        return self.add(event)

    def for_actor(self, actor_id: str, *, limit: int = 100) -> Sequence[AuditEvent]:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.actor_id == actor_id)
            .order_by(col(AuditEvent.real_time).desc())
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def for_transaction(self, transaction_id: str) -> Sequence[AuditEvent]:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.transaction_id == transaction_id)
            .order_by(col(AuditEvent.real_time))
        )
        return self.session.exec(statement).all()

    def recent_for_room(
        self, room_id: str, *, limit: int = 50, since_id: int | None = None
    ) -> Sequence[AuditEvent]:
        """Recent audit events for a room (good source for game feed)."""
        stmt = select(AuditEvent).where(AuditEvent.room_id == room_id)
        if since_id is not None:
            stmt = stmt.where(col(AuditEvent.id) > since_id)
        stmt = stmt.order_by(col(AuditEvent.real_time)).limit(limit)
        return self.session.exec(stmt).all()

    def recent_for_actor(
        self, actor_id: str, *, limit: int = 50, since_id: int | None = None
    ) -> Sequence[AuditEvent]:
        stmt = select(AuditEvent).where(AuditEvent.actor_id == actor_id)
        if since_id is not None:
            stmt = stmt.where(col(AuditEvent.id) > since_id)
        stmt = stmt.order_by(col(AuditEvent.real_time)).limit(limit)
        return self.session.exec(stmt).all()
