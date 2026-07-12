"""Admin API router for engine operations — request a process restart (Sprint 72.3a).

This is the *safe half* of the restart story: the endpoint only **requests** a
restart by writing a sentinel file that the out-of-process supervisor
(``scripts/supervisor.py``, 72.3b) watches; no process-lifecycle code runs in
the request path. It is admin-gated (superadmin to trigger), audit-logged, has a
confirmation gate, and exposes an "armed?" indicator derived from the
supervisor's heartbeat so clicking restart with no performer wired returns a
clear error instead of a silent no-op.

Lives entirely in the composition layer (``webui.admin``): touches only the
control-directory files via ``lorecraft.ops`` and the audit DB — no engine
mutation, no tier violation, no hardcoded world content.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.transaction import TransactionSource
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.repos.audit_repo import AuditRepo
from lorecraft.ops.restart_control import RestartControl, SupervisorStatus
from lorecraft.webui.admin.auth import Observer, Superadmin

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


def _control(state: Any) -> RestartControl:
    return RestartControl(state.settings.control_dir)


def _status_payload(status: SupervisorStatus) -> dict[str, Any]:
    return {
        "armed": status.armed,
        "pid": status.pid,
        "started_at": status.started_at,
        "heartbeat_at": status.heartbeat_at,
        "heartbeat_age": status.heartbeat_age,
    }


@router.get("/ops/restart")
async def restart_status(request: Request, _: Observer) -> dict[str, Any]:
    """Report whether a supervisor is armed to perform a restart."""
    state = _state(request)
    return _status_payload(_control(state).read_status())


class _RestartBody(BaseModel):
    # Explicit confirmation gate: a bare POST does nothing.
    confirm: bool = False
    reason: str | None = None


@router.post("/ops/restart")
async def request_restart(
    body: _RestartBody, request: Request, admin: Superadmin
) -> dict[str, Any]:
    """Request a graceful engine restart (superadmin, confirm-gated, audited)."""
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Restart not confirmed. Set confirm=true to proceed.",
        )

    state = _state(request)
    control = _control(state)
    status = control.read_status()
    if not status.armed:
        # Never a silent no-op: with no performer listening, say so.
        raise HTTPException(
            status_code=409,
            detail=(
                "No supervisor is armed to perform the restart. Start the engine "
                "via the supervisor (scripts/supervisor.py) to enable restarts."
            ),
        )

    request_record = control.request_restart(
        requested_by=admin.username, reason=body.reason
    )
    _audit_restart_request(state, admin.username, body.reason)

    return {
        "status": "restart_requested",
        "requested_by": request_record.requested_by,
        "requested_at": request_record.requested_at,
        "reason": request_record.reason,
        "supervisor": _status_payload(status),
    }


def _audit_restart_request(state: Any, username: str, reason: str | None) -> None:
    """Record the restart request in the audit log."""
    with Session(state.audit_engine) as audit_session:
        AuditRepo(audit_session).record(
            AuditEvent(
                transaction_id=str(uuid4()),
                correlation_id=f"admin-restart-{int(time.time() * 1000)}",
                actor_id=username,
                event_type=GameEvent.ENGINE_RESTART_REQUESTED.value,
                source_type=TransactionSource.ADMIN.value,
                room_id="",
                game_time=0.0,
                real_time=time.time(),
                severity="WARNING",
                summary=f"Admin '{username}' requested an engine restart.",
                payload_json={"reason": reason},
            )
        )
        audit_session.commit()
