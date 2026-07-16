"""Admin API router for audit log queries and session replay."""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from sqlmodel import Session, col, func, select

from lorecraft.webui.admin.auth import Observer
from lorecraft.engine.models.audit import AuditEvent

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


def _serialize_event(e: AuditEvent) -> dict[str, Any]:
    return {
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


def _audit_statement(
    *,
    actor: str | None = None,
    room: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    source_type: str | None = None,
    target: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
) -> Any:
    stmt = select(AuditEvent).order_by(col(AuditEvent.real_time).desc())
    if actor:
        stmt = stmt.where(AuditEvent.actor_id == actor)
    if room:
        stmt = stmt.where(AuditEvent.room_id == room)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if severity:
        stmt = stmt.where(AuditEvent.severity == severity)
    if source_type:
        stmt = stmt.where(AuditEvent.source_type == source_type)
    if target:
        stmt = stmt.where(AuditEvent.target_id == target)
    if from_ts is not None:
        stmt = stmt.where(col(AuditEvent.real_time) >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(col(AuditEvent.real_time) <= to_ts)
    return stmt


@router.get("/audit")
async def query_audit(
    request: Request,
    _: Observer,
    actor: str | None = None,
    room: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    source_type: str | None = None,
    target: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.audit_engine) as session:
        stmt = _audit_statement(
            actor=actor,
            room=room,
            event_type=event_type,
            severity=severity,
            source_type=source_type,
            target=target,
            from_ts=from_ts,
            to_ts=to_ts,
        ).limit(min(limit, 1000))
        events = session.exec(stmt).all()
    return [_serialize_event(e) for e in events]


@router.get("/audit/export")
async def export_audit(
    request: Request,
    _: Observer,
    actor: str | None = None,
    room: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    source_type: str | None = None,
    target: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    limit: int = 1000,
    format: str = "json",
) -> Response:
    state = _state(request)
    with Session(state.audit_engine) as session:
        events = session.exec(
            _audit_statement(
                actor=actor,
                room=room,
                event_type=event_type,
                severity=severity,
                source_type=source_type,
                target=target,
                from_ts=from_ts,
                to_ts=to_ts,
            ).limit(min(limit, 5000))
        ).all()
    rows = [_serialize_event(e) for e in events]
    if format == "json":
        import json

        return Response(
            json.dumps(rows),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=audit-export.json"},
        )
    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "id",
                "real_time",
                "event_type",
                "actor_id",
                "source_type",
                "target_id",
                "room_id",
                "severity",
                "summary",
                "transaction_id",
                "correlation_id",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in writer.fieldnames})
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit-export.csv"},
        )
    raise HTTPException(status_code=422, detail="format must be json or csv")


@router.get("/audit/facets")
async def audit_facets(request: Request, _: Observer) -> dict[str, Any]:
    state = _state(request)
    with Session(state.audit_engine) as session:

        def counts(column: Any) -> list[dict[str, Any]]:
            rows = session.exec(
                select(column, func.count())
                .group_by(column)
                .order_by(func.count().desc())
                .limit(100)
            ).all()
            return [{"value": value or "", "count": count} for value, count in rows]

        return {
            "event_types": counts(AuditEvent.event_type),
            "actors": counts(AuditEvent.actor_id),
            "rooms": counts(AuditEvent.room_id),
            "severities": counts(AuditEvent.severity),
            "sources": counts(AuditEvent.source_type),
        }


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
    return [_serialize_event(e) for e in events]
