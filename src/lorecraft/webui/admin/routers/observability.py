"""Admin API router for request tracing and crash reports (Sprint 57)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlmodel import Session, col, select

from lorecraft.engine.models.audit import CrashReport
from lorecraft.observability import get_trace
from lorecraft.webui.admin.auth import Observer

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


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
