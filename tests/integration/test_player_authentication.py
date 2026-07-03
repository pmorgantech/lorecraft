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
    player_session_secret="test-player-secret-32-chars-long!",  # gitleaks:allow
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


async def _run_websocket(
    app: Any, *, query_string: bytes, incoming: list[AsgiMessage]
) -> list[AsgiMessage]:
    messages: list[AsgiMessage] = []
    receive_tx, receive_rx = anyio.create_memory_object_stream[AsgiMessage](16)

    async def receive() -> AsgiMessage:
        return await receive_rx.receive()

    async def send(message: AsgiMessage) -> None:
        messages.append(message)

    async with receive_tx, receive_rx:
        for message in incoming:
            await receive_tx.send(message)

        with anyio.fail_after(5):
            await app(
                {
                    "type": "websocket",
                    "asgi": {"version": "3.0", "spec_version": "2.4"},
                    "scheme": "ws",
                    "path": "/ws",
                    "raw_path": b"/ws",
                    "query_string": query_string,
                    "headers": [],
                    "client": ("testclient", 50000),
                    "server": ("testserver", 80),
                    "subprotocols": [],
                    "state": {},
                },
                receive,
                send,
            )
    return messages


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


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


def test_refresh_issues_new_access_and_refresh_tokens() -> None:
    anyio.run(_test_refresh_issues_new_access_and_refresh_tokens)


async def _test_refresh_issues_new_access_and_refresh_tokens() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        _, login_data = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "refresher", "password": "hunter2"},
        )
        status, data = await _http(
            app,
            "POST",
            "/auth/refresh",
            body={"refresh_token": login_data["refresh_token"]},
        )
    assert status == 200
    assert data["player_id"] == login_data["player_id"]
    assert data["access_token"] != login_data["access_token"]
    assert data["refresh_token"] != login_data["refresh_token"]


def test_refresh_rejects_access_token() -> None:
    anyio.run(_test_refresh_rejects_access_token)


async def _test_refresh_rejects_access_token() -> None:
    """An access token presented as a refresh token must be rejected."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        _, login_data = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "confused", "password": "hunter2"},
        )
        status, _ = await _http(
            app,
            "POST",
            "/auth/refresh",
            body={"refresh_token": login_data["access_token"]},
        )
    assert status == 401


def test_refresh_rejects_garbage_token() -> None:
    anyio.run(_test_refresh_rejects_garbage_token)


async def _test_refresh_rejects_garbage_token() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/auth/refresh",
            body={"refresh_token": "not-a-jwt"},
        )
    assert status == 401


def test_refresh_rejects_expired_refresh_token() -> None:
    anyio.run(_test_refresh_rejects_expired_refresh_token)


async def _test_refresh_rejects_expired_refresh_token() -> None:
    from lorecraft.web.auth import issue_refresh_token

    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        _, login_data = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "expired_refresh", "password": "hunter2"},
        )
        expired_token = issue_refresh_token(
            login_data["player_id"],
            _SETTINGS.player_session_secret,
            ttl_seconds=-1,
        )
        status, _ = await _http(
            app,
            "POST",
            "/auth/refresh",
            body={"refresh_token": expired_token},
        )
    assert status == 401


# ---------------------------------------------------------------------------
# POST /auth/ws-ticket + /ws?ticket= handshake
# ---------------------------------------------------------------------------

_NO_LEGACY_SETTINGS = Settings(
    database_path=":memory:",
    audit_database_path=":memory:",
    player_session_secret="test-player-secret-32-chars-long!",  # gitleaks:allow
    allow_query_player_id=False,
)


def test_ws_ticket_issued_with_bearer_token_connects_over_ws() -> None:
    anyio.run(_test_ws_ticket_issued_with_bearer_token_connects_over_ws)


async def _test_ws_ticket_issued_with_bearer_token_connects_over_ws() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_NO_LEGACY_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        _, login_data = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "ticketholder", "password": "hunter2"},
        )
        status, ticket_data = await _http(
            app, "POST", "/auth/ws-ticket", token=login_data["access_token"]
        )
        assert status == 200
        ticket = ticket_data["ws_ticket"]

        messages = await _run_websocket(
            app,
            query_string=f"ticket={ticket}".encode(),
            incoming=[
                {"type": "websocket.connect"},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )
    payloads = [
        json.loads(m["text"]) for m in messages if m["type"] == "websocket.send"
    ]
    assert payloads[0]["type"] == "connected"
    assert payloads[0]["player_id"] == login_data["player_id"]


def test_ws_ticket_is_single_use() -> None:
    anyio.run(_test_ws_ticket_is_single_use)


async def _test_ws_ticket_is_single_use() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_NO_LEGACY_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        _, login_data = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "onetimer", "password": "hunter2"},
        )
        _, ticket_data = await _http(
            app, "POST", "/auth/ws-ticket", token=login_data["access_token"]
        )
        ticket = ticket_data["ws_ticket"]

        first_connect = await _run_websocket(
            app,
            query_string=f"ticket={ticket}".encode(),
            incoming=[
                {"type": "websocket.connect"},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )
        second_connect = await _run_websocket(
            app,
            query_string=f"ticket={ticket}".encode(),
            incoming=[{"type": "websocket.connect"}],
        )
    first_payloads = [
        json.loads(m["text"]) for m in first_connect if m["type"] == "websocket.send"
    ]
    assert first_payloads[0]["type"] == "connected"

    close_messages = [m for m in second_connect if m["type"] == "websocket.close"]
    assert len(close_messages) == 1
    assert close_messages[0]["code"] == 1008


def test_ws_ticket_request_rejects_expired_access_token() -> None:
    anyio.run(_test_ws_ticket_request_rejects_expired_access_token)


async def _test_ws_ticket_request_rejects_expired_access_token() -> None:
    from lorecraft.web.auth import issue_access_token

    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_NO_LEGACY_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        _, login_data = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "expired_access", "password": "hunter2"},
        )
        expired_token = issue_access_token(
            login_data["player_id"],
            _NO_LEGACY_SETTINGS.player_session_secret,
            ttl_seconds=-1,
        )
        status, _ = await _http(app, "POST", "/auth/ws-ticket", token=expired_token)
    assert status == 401


def test_ws_rejects_missing_ticket_when_legacy_fallback_disabled() -> None:
    anyio.run(_test_ws_rejects_missing_ticket_when_legacy_fallback_disabled)


async def _test_ws_rejects_missing_ticket_when_legacy_fallback_disabled() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_NO_LEGACY_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        messages = await _run_websocket(
            app,
            query_string=b"player_id=player-1",
            incoming=[{"type": "websocket.connect"}],
        )
    close_messages = [m for m in messages if m["type"] == "websocket.close"]
    assert len(close_messages) == 1
    assert close_messages[0]["code"] == 1008


def test_ws_ticket_expires_after_ttl() -> None:
    anyio.run(_test_ws_ticket_expires_after_ttl)


async def _test_ws_ticket_expires_after_ttl() -> None:
    """A ticket past its TTL is rejected even if never explicitly consumed —
    covers the expiry branch in consume_ws_ticket() distinct from the
    single-use (already-consumed) case tested above."""
    from lorecraft.state import AppState
    from lorecraft.web.auth import consume_ws_ticket, issue_ws_ticket

    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_NO_LEGACY_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        state = app.state.lorecraft
        assert isinstance(state, AppState)
        ticket = issue_ws_ticket(state, "some-player-id")
        # Force it into the past rather than sleeping past a real TTL.
        player_id, _ = state.ws_tickets[ticket]
        state.ws_tickets[ticket] = (player_id, 0.0)

        assert consume_ws_ticket(state, ticket) is None


def test_ws_ticket_via_session_cookie() -> None:
    anyio.run(_test_ws_ticket_via_session_cookie)


async def _test_ws_ticket_via_session_cookie() -> None:
    """The browser lobby login path (no bearer token) can also mint a ticket
    using its signed `lorecraft_session` cookie."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_NO_LEGACY_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    from lorecraft.web.player_auth import PLAYER_SESSION_COOKIE, create_player_token

    async with _lifespan(app):
        _, login_data = await _http(
            app,
            "POST",
            "/auth/login",
            body={"username": "cookieuser", "password": "hunter2"},
        )
        player_id = login_data["player_id"]
        cookie_token = create_player_token(
            player_id,
            _NO_LEGACY_SETTINGS.player_session_secret,  # gitleaks:allow
            ttl_seconds=3600,
        )

        sent = False
        messages: list[AsgiMessage] = []

        async def receive() -> AsgiMessage:
            nonlocal sent
            if sent:
                await anyio.sleep_forever()
            sent = True
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: AsgiMessage) -> None:
            messages.append(msg)

        with anyio.fail_after(5):
            await app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "method": "POST",
                    "scheme": "http",
                    "path": "/auth/ws-ticket",
                    "raw_path": b"/auth/ws-ticket",
                    "query_string": b"",
                    "headers": [
                        (
                            b"cookie",
                            f"{PLAYER_SESSION_COOKIE}={cookie_token}".encode(),
                        )
                    ],
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
    assert status == 200
    assert "ws_ticket" in json.loads(body_bytes)


# ---------------------------------------------------------------------------
# POST /auth/oauth/{provider}/callback (Sprint 4.7 extensibility stub)
# ---------------------------------------------------------------------------


def test_oauth_callback_stub_returns_501() -> None:
    anyio.run(_test_oauth_callback_stub_returns_501)


async def _test_oauth_callback_stub_returns_501() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, _ = await _http(app, "POST", "/auth/oauth/google/callback")
    assert status == 501
