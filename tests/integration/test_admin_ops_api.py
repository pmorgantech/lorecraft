"""Integration tests for the admin engine-restart endpoint (Sprint 72.3a)."""

from __future__ import annotations

import json
import tempfile
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import anyio
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from lorecraft.config import Settings
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.main import create_app
from lorecraft.models.admin import AdminUser
from lorecraft.ops.restart_control import RestartControl
from lorecraft.webui.admin.auth import create_token, hash_password

_SECRET = "test-jwt-secret-for-ops-tests!!"

AsgiMessage = dict[str, Any]


def _make_engines() -> tuple[Any, Any]:
    from lorecraft.db import create_tables

    game = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    audit = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(game_engine=game, audit_engine=audit)
    return game, audit


def _settings(control_dir: str) -> Settings:
    return Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        control_dir=control_dir,
    )


def _access_token(role: str = "superadmin") -> str:
    return create_token("testadmin", role, _SECRET, 900, "access")


def _seed_admin(game_engine: Any, role: str = "superadmin") -> None:
    with Session(game_engine) as session:
        session.add(
            AdminUser(
                id=str(uuid.uuid4()),
                username="testadmin",
                password_hash=hash_password("password"),
                role=role,
                created_at=time.time(),
            )
        )
        session.commit()


@asynccontextmanager
async def _lifespan(app: Any) -> AsyncIterator[None]:
    recv_tx, recv_rx = anyio.create_memory_object_stream[AsgiMessage](4)
    send_tx, send_rx = anyio.create_memory_object_stream[AsgiMessage](4)
    async with recv_tx, recv_rx, send_tx, send_rx, anyio.create_task_group() as tg:
        tg.start_soon(
            app,
            {"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}},
            recv_rx.receive,
            send_tx.send,
        )
        await recv_tx.send({"type": "lifespan.startup"})
        startup = await send_rx.receive()
        assert startup == {"type": "lifespan.startup.complete"}
        try:
            yield
        finally:
            await recv_tx.send({"type": "lifespan.shutdown"})
            shutdown = await send_rx.receive()
            assert shutdown == {"type": "lifespan.shutdown.complete"}


async def _http(
    app: Any, method: str, path: str, *, body: Any = None, token: str = ""
) -> tuple[int, Any]:
    sent = False
    messages: list[AsgiMessage] = []
    raw_body = json.dumps(body).encode() if body is not None else b""

    async def receive() -> AsgiMessage:
        nonlocal sent
        if sent:
            await anyio.sleep_forever()
        sent = True
        return {"type": "http.request", "body": raw_body, "more_body": False}

    async def send(msg: AsgiMessage) -> None:
        messages.append(msg)

    headers: list[tuple[bytes, bytes]] = [(b"content-type", b"application/json")]
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))

    with anyio.fail_after(5):
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "method": method.upper(),
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": headers,
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "state": {},
            },
            receive,
            send,
        )
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body_bytes = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return status, json.loads(body_bytes) if body_bytes else {}


def _arm(control_dir: str) -> None:
    """Publish a fresh heartbeat so the endpoint sees a performer as armed."""
    RestartControl(control_dir).write_heartbeat(pid=99999, started_at=time.time())


# ---------------------------------------------------------------------------


def test_status_reports_not_armed_without_supervisor() -> None:
    anyio.run(_run_status_not_armed)


async def _run_status_not_armed() -> None:
    with tempfile.TemporaryDirectory() as control_dir:
        game, audit = _make_engines()
        app = create_app(
            settings=_settings(control_dir), game_engine=game, audit_engine=audit
        )
        async with _lifespan(app):
            _seed_admin(game)
            status, data = await _http(
                app, "GET", "/admin/ops/restart", token=_access_token()
            )
    assert status == 200
    assert data["armed"] is False


def test_status_reports_armed_with_fresh_heartbeat() -> None:
    anyio.run(_run_status_armed)


async def _run_status_armed() -> None:
    with tempfile.TemporaryDirectory() as control_dir:
        _arm(control_dir)
        game, audit = _make_engines()
        app = create_app(
            settings=_settings(control_dir), game_engine=game, audit_engine=audit
        )
        async with _lifespan(app):
            _seed_admin(game)
            status, data = await _http(
                app, "GET", "/admin/ops/restart", token=_access_token()
            )
    assert status == 200
    assert data["armed"] is True
    assert data["pid"] == 99999


def test_restart_without_confirm_is_rejected() -> None:
    anyio.run(_run_no_confirm)


async def _run_no_confirm() -> None:
    with tempfile.TemporaryDirectory() as control_dir:
        _arm(control_dir)
        game, audit = _make_engines()
        app = create_app(
            settings=_settings(control_dir), game_engine=game, audit_engine=audit
        )
        async with _lifespan(app):
            _seed_admin(game)
            status, _ = await _http(
                app,
                "POST",
                "/admin/ops/restart",
                body={"confirm": False},
                token=_access_token(),
            )
    assert status == 400


def test_restart_without_armed_supervisor_is_409_not_silent() -> None:
    anyio.run(_run_not_armed_409)


async def _run_not_armed_409() -> None:
    with tempfile.TemporaryDirectory() as control_dir:
        game, audit = _make_engines()
        app = create_app(
            settings=_settings(control_dir), game_engine=game, audit_engine=audit
        )
        async with _lifespan(app):
            _seed_admin(game)
            status, data = await _http(
                app,
                "POST",
                "/admin/ops/restart",
                body={"confirm": True},
                token=_access_token(),
            )
        # No sentinel should have been written when nothing is listening.
        assert not RestartControl(control_dir).request_path.exists()
    assert status == 409
    assert "supervisor" in data["detail"].lower()


def test_confirmed_restart_writes_sentinel_and_audits() -> None:
    anyio.run(_run_confirmed)


async def _run_confirmed() -> None:
    with tempfile.TemporaryDirectory() as control_dir:
        _arm(control_dir)
        game, audit = _make_engines()
        app = create_app(
            settings=_settings(control_dir), game_engine=game, audit_engine=audit
        )
        async with _lifespan(app):
            _seed_admin(game)
            status, data = await _http(
                app,
                "POST",
                "/admin/ops/restart",
                body={"confirm": True, "reason": "deploy v2"},
                token=_access_token(),
            )
            # The supervisor would consume this; here we just assert it landed.
            request = RestartControl(control_dir).take_request()
            with Session(audit) as session:
                events = session.exec(
                    select(AuditEvent).where(
                        AuditEvent.event_type
                        == GameEvent.ENGINE_RESTART_REQUESTED.value
                    )
                ).all()

    assert status == 200
    assert data["status"] == "restart_requested"
    assert data["requested_by"] == "testadmin"
    assert request is not None
    assert request.reason == "deploy v2"
    assert len(events) == 1
    assert events[0].actor_id == "testadmin"


def test_restart_requires_superadmin() -> None:
    anyio.run(_run_requires_superadmin)


async def _run_requires_superadmin() -> None:
    with tempfile.TemporaryDirectory() as control_dir:
        _arm(control_dir)
        game, audit = _make_engines()
        app = create_app(
            settings=_settings(control_dir), game_engine=game, audit_engine=audit
        )
        async with _lifespan(app):
            _seed_admin(game, role="moderator")
            status, _ = await _http(
                app,
                "POST",
                "/admin/ops/restart",
                body={"confirm": True},
                token=_access_token(role="moderator"),
            )
    assert status == 403
