"""Audit event recording service."""

from __future__ import annotations

import time

from lorecraft.game.context import GameContext
from lorecraft.game.events import GameEvent
from lorecraft.models.audit import AuditEvent
from lorecraft.repos.audit_repo import AuditRepo
from lorecraft.types import JsonObject


class AuditService:
    def __init__(self, audit_repo: AuditRepo | None) -> None:
        self.audit_repo = audit_repo

    @classmethod
    def from_context(cls, ctx: GameContext) -> "AuditService":
        return cls(ctx.audit)

    def record(
        self,
        ctx: GameContext,
        event_type: GameEvent,
        *,
        target_id: str | None = None,
        severity: str = "INFO",
        summary: str = "",
        payload: JsonObject | None = None,
    ) -> AuditEvent | None:
        if self.audit_repo is None:
            return None

        event = AuditEvent(
            transaction_id=ctx.transaction.transaction_id,
            correlation_id=ctx.transaction.correlation_id,
            parent_transaction_ids=ctx.transaction.parent_transaction_ids,
            actor_id=ctx.transaction.actor_id,
            event_type=event_type.value,
            source_type=ctx.transaction.source_type.value,
            target_id=target_id,
            room_id=ctx.room.id,
            game_time=ctx.clock.game_epoch if ctx.clock is not None else 0.0,
            real_time=time.time(),
            severity=severity,
            summary=summary,
            payload_json=payload or {},
        )
        return self.audit_repo.record(event)
