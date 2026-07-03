"""Integration tests for player-facing authentication (Sprint 4).

Covers `POST /auth/login`, `/auth/refresh`, `/auth/ws-ticket`, and the raw
`/ws` handshake ticket validation — the full account-creation/login/token/
WS-connect lifecycle over the real ASGI app.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import anyio
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from lorecraft.config import Settings
from lorecraft.main import create_app
from lorecraft.models.player_auth import PlayerAuth

AsgiMessage = dict[str, Any]

_SETTINGS = Settings(
    database_path=":memory:",
    audit_database_path=":memory:",
    player_session_secret="test-player-secret-32-chars-long!",
)


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


async def _http(
    app: Any, method: str, path: str, *, body: Any = None, token: str = ""
) -> Any:
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

    raw_path, _sep, query_string = path.partition("?")

    with anyio.fail_after(5):
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "method": method.upper(),
                "scheme": "http",
                "path": raw_path,
                "raw_path": raw_path.encode(),
                "query_string": query_string.encode(),
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


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


def test_login_creates_account_on_first_use() -> None:
    anyio.run(_test_login_creates_account_on_first_use)


async def _test_login_creates_account_on_first_use() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "brandnew", "password": "hunter2"},
        )
    assert status == 200
    assert data["created"] is True
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    with Session(game_engine) as session:
        auths = session.exec(select(PlayerAuth)).all()
    assert any(a.provider_subject == "brandnew" for a in auths)


def test_login_verifies_password_on_repeat_use() -> None:
    anyio.run(_test_login_verifies_password_on_repeat_use)


async def _test_login_verifies_password_on_repeat_use() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        first_status, first_data = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "returning", "password": "correct-horse"},
        )
        assert first_status == 200
        second_status, second_data = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "returning", "password": "correct-horse"},
        )
    assert second_status == 200
    assert second_data["created"] is False
    assert second_data["player_id"] == first_data["player_id"]


def test_login_wrong_password_returns_401() -> None:
    anyio.run(_test_login_wrong_password_returns_401)


async def _test_login_wrong_password_returns_401() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "someone", "password": "right-password"},
        )
        status, _ = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "someone", "password": "wrong-password"},
        )
    assert status == 401


def test_login_invalid_username_returns_400() -> None:
    anyio.run(_test_login_invalid_username_returns_400)


async def _test_login_invalid_username_returns_400() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "a", "password": "hunter2"},
        )
    assert status == 400
