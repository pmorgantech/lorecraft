"""Admin API router for audit log queries and session replay."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlmodel import Session, col, select

from lorecraft.admin.auth import Observer
from lorecraft.models.audit import AuditEvent

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


@router.get("/audit")
async def query_audit(
    request: Request,
    _: Observer,
    actor: str | None = None,
    room: str | None = None,
    event_type: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.audit_engine) as session:
        stmt = select(AuditEvent).order_by(col(AuditEvent.real_time).desc())
        if actor:
            stmt = stmt.where(AuditEvent.actor_id == actor)
        if room:
            stmt = stmt.where(AuditEvent.room_id == room)
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
        if from_ts is not None:
            stmt = stmt.where(col(AuditEvent.real_time) >= from_ts)
        if to_ts is not None:
            stmt = stmt.where(col(AuditEvent.real_time) <= to_ts)
        stmt = stmt.limit(min(limit, 1000))
        events = session.exec(stmt).all()
    return [
        {
            "id": e.id,
            "transaction_id": e.transaction_id,
            "correlation_id": e.correlation_id,
            "actor_id": e.actor_id,
            "event_type": e.event_type,
            "source_type": e.source_type,
            "target_id": e.target_id,
            "room_id": e.room_id,
            "game_time": e.game_time,
            "real_time": e.real_time,
            "severity": e.severity,
            "summary": e.summary,
            "payload": e.payload_json,
        }
        for e in events
    ]


@router.get("/audit/session/{correlation_id}")
async def session_replay(
    correlation_id: str, request: Request, _: Observer
) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.audit_engine) as session:
        events = session.exec(
            select(AuditEvent)
            .where(AuditEvent.correlation_id == correlation_id)
            .order_by(col(AuditEvent.real_time))
        ).all()
    return [
        {
            "id": e.id,
            "transaction_id": e.transaction_id,
            "actor_id": e.actor_id,
            "event_type": e.event_type,
            "source_type": e.source_type,
            "target_id": e.target_id,
            "room_id": e.room_id,
            "game_time": e.game_time,
            "real_time": e.real_time,
            "severity": e.severity,
            "summary": e.summary,
            "payload": e.payload_json,
        }
        for e in events
    ]
