"""Admin API router for request tracing and crash reports (Sprint 57)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlmodel import Session, col, func, select

from lorecraft.engine.models.audit import AuditEvent, CrashReport
from lorecraft.engine.models.scheduler import ScheduledJob
from lorecraft.engine.models.session import PlayerSession
from lorecraft.observability import get_trace
from lorecraft.webui.admin.auth import Observer

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


@router.get("/system/health")
async def system_health(request: Request, _: Observer) -> dict[str, Any]:
    """Read-only admin health summary grounded in existing runtime/audit data."""
    state = _state(request)
    online_connections = len(state.manager._connections)
    with Session(state.game_engine) as game_session:
        pending_jobs = game_session.exec(
            select(func.count())
            .select_from(ScheduledJob)
            .where(ScheduledJob.status == "pending")
        ).one()
        active_sessions = game_session.exec(
            select(func.count())
            .select_from(PlayerSession)
            .where(PlayerSession.status == "active")
        ).one()
    with Session(state.audit_engine) as audit_session:
        recent_errors = audit_session.exec(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.severity.in_(["ERROR", "CRITICAL"]))
        ).one()
        crash_count = audit_session.exec(
            select(func.count()).select_from(CrashReport)
        ).one()
    return {
        "websocket_connections": online_connections,
        "active_player_sessions": active_sessions,
        "pending_scheduler_jobs": pending_jobs,
        "audit_errors_total": recent_errors,
        "crash_reports_total": crash_count,
        "eventbus_metrics": state.bus.metrics_snapshot(),
    }


@router.get("/system/scheduler")
async def scheduler_timeline(
    request: Request, _: Observer, limit: int = 50
) -> list[dict[str, Any]]:
    """Pending scheduler jobs, soonest first."""
    state = _state(request)
    with Session(state.game_engine) as session:
        jobs = session.exec(
            select(ScheduledJob)
            .where(ScheduledJob.status == "pending")
            .order_by(col(ScheduledJob.due_at_epoch))
            .limit(min(limit, 200))
        ).all()
    return [
        {
            "id": job.id,
            "job_type": job.job_type,
            "due_at_epoch": job.due_at_epoch,
            "created_at": job.created_at,
            "payload": job.payload,
        }
        for job in jobs
    ]


@router.get("/trace/{transaction_id}")
async def get_command_trace(transaction_id: str, _: Observer) -> list[dict[str, Any]]:
    """The captured spans for one recent command (Sprint 57.1's in-memory ring
    buffer — not persisted, so this only covers the last `_TRACE_BUFFER_MAX`
    commands server-wide). 404 once a transaction ages out or was never
    bound (typos, ids from before the last restart)."""
    spans = get_trace(transaction_id)
    if spans is None:
        raise HTTPException(
            status_code=404,
            detail="No trace for that transaction id (aged out, unknown, or pre-restart).",
        )
    return [
        {
            "name": s.name,
            "duration_ms": round(s.duration_ms, 3),
            "started_at": s.started_at,
        }
        for s in spans
    ]


def _crash_summary(c: CrashReport) -> dict[str, Any]:
    return {
        "id": c.id,
        "transaction_id": c.transaction_id,
        "correlation_id": c.correlation_id,
        "player_id": c.player_id,
        "command_text": c.command_text,
        "real_time": c.real_time,
    }


@router.get("/crashes")
async def list_crashes(
    request: Request, _: Observer, limit: int = 100
) -> list[dict[str, Any]]:
    """Recent crash reports (Sprint 57.3), newest first."""
    state = _state(request)
    with Session(state.audit_engine) as session:
        stmt = (
            select(CrashReport)
            .order_by(col(CrashReport.real_time).desc())
            .limit(min(limit, 1000))
        )
        crashes = session.exec(stmt).all()
    return [_crash_summary(c) for c in crashes]


@router.get("/crashes/{crash_id}")
async def get_crash(crash_id: int, request: Request, _: Observer) -> dict[str, Any]:
    """One crash report's full detail, including the stack trace."""
    state = _state(request)
    with Session(state.audit_engine) as session:
        crash = session.get(CrashReport, crash_id)
    if crash is None:
        raise HTTPException(status_code=404, detail="No crash report with that id.")
    return {**_crash_summary(crash), "stack_trace": crash.stack_trace}
