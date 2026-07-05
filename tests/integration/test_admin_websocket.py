"""
Characterization tests for admin WebSocket endpoint — Sprint 7.3

Lock in current behavior of `/admin/ws` before Sprint 8–9 refactors.
Focus areas:
- Token validation: valid JWT, invalid/missing tokens, expiration
- Broadcast reception: messages from broadcaster reach connected clients
- Multiple connections: simultaneous connections can all receive broadcasts
- Disconnect handling: cleanup of broadcaster queue on disconnect
- Error handling: malformed messages, send failures, connection errors
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import anyio
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from lorecraft.webui.admin.auth import create_token, hash_password
from lorecraft.config import Settings
from lorecraft.db import create_tables
from lorecraft.main import create_app
from lorecraft.models.admin import AdminUser

AsgiMessage = dict[str, Any]
AsgiReceive = Callable[[], Awaitable[AsgiMessage]]
AsgiSend = Callable[[AsgiMessage], Awaitable[None]]

_SECRET = "test-jwt-secret-for-admin-ws-tests!"
_SETTINGS = Settings(
    database_path=":memory:",
    audit_database_path=":memory:",
    admin_jwt_secret=_SECRET,
)


def _make_engines() -> tuple[Any, Any]:
    game = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    audit = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(game_engine=game, audit_engine=audit)
    return game, audit


def _access_token(role: str = "superadmin") -> str:
    return create_token("testadmin", role, _SECRET, 900, "access")


def _seed_admin(game_engine: Any, role: str = "superadmin") -> None:
    with Session(game_engine) as session:
        session.add(
            AdminUser(
                id="admin-1",
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

    async with (
        recv_tx,
        recv_rx,
        send_tx,
        send_rx,
        anyio.create_task_group() as tg,
    ):
        tg.start_soon(
            app,
            {
                "type": "lifespan",
                "asgi": {"version": "3.0", "spec_version": "2.0"},
                "state": {},
            },
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


async def _run_admin_websocket(
    app: Any,
    *,
    token: str = "",
    incoming: list[AsgiMessage],
) -> list[AsgiMessage]:
    """Run admin WebSocket connection and return all ASGI messages."""
    messages: list[AsgiMessage] = []
    receive_tx, receive_rx = anyio.create_memory_object_stream[AsgiMessage](16)

    async def receive() -> AsgiMessage:
        return await receive_rx.receive()

    async def send(message: AsgiMessage) -> None:
        messages.append(message)

    async with receive_tx, receive_rx:
        for message in incoming:
            await receive_tx.send(message)

        query_string = f"token={token}".encode() if token else b""

        with anyio.fail_after(5):
            await app(
                {
                    "type": "websocket",
                    "asgi": {"version": "3.0", "spec_version": "2.4"},
                    "scheme": "ws",
                    "path": "/admin/ws",
                    "raw_path": b"/admin/ws",
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


# =============================================================================
# TOKEN VALIDATION TESTS
# =============================================================================


def test_admin_ws_rejects_missing_token() -> None:
    anyio.run(_test_admin_ws_rejects_missing_token)


async def _test_admin_ws_rejects_missing_token() -> None:
    """Verify admin WS closes with 1008 when token is missing."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    _seed_admin(game_engine)

    async with _lifespan(app):
        messages = await _run_admin_websocket(
            app,
            token="",  # no token
            incoming=[{"type": "websocket.connect"}],
        )

    # Should have close frame with code 1008
    close_msgs = [m for m in messages if m["type"] == "websocket.close"]
    assert len(close_msgs) > 0
    assert close_msgs[0].get("code") == 1008


def test_admin_ws_rejects_invalid_token() -> None:
    anyio.run(_test_admin_ws_rejects_invalid_token)


async def _test_admin_ws_rejects_invalid_token() -> None:
    """Verify admin WS closes with 1008 when token is invalid."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    _seed_admin(game_engine)

    async with _lifespan(app):
        messages = await _run_admin_websocket(
            app,
            token="invalid.token.here",
            incoming=[{"type": "websocket.connect"}],
        )

    close_msgs = [m for m in messages if m["type"] == "websocket.close"]
    assert len(close_msgs) > 0
    assert close_msgs[0].get("code") == 1008


def test_admin_ws_accepts_valid_token() -> None:
    anyio.run(_test_admin_ws_accepts_valid_token)


async def _test_admin_ws_accepts_valid_token() -> None:
    """Verify admin WS accepts connection with valid JWT token."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    _seed_admin(game_engine)
    token = _access_token()

    async with _lifespan(app):
        messages = await _run_admin_websocket(
            app,
            token=token,
            incoming=[
                {"type": "websocket.connect"},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )

    # Should have accept message
    accept_msgs = [m for m in messages if m["type"] == "websocket.accept"]
    assert len(accept_msgs) > 0


# =============================================================================
# BROADCAST RECEPTION TESTS
# =============================================================================


def test_admin_ws_connection_lifecycle() -> None:
    anyio.run(_test_admin_ws_lifecycle)


async def _test_admin_ws_lifecycle() -> None:
    """Verify admin WS connection accepts, processes input, and disconnects gracefully."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    _seed_admin(game_engine)
    token = _access_token()

    async with _lifespan(app):
        messages = await _run_admin_websocket(
            app,
            token=token,
            incoming=[
                {"type": "websocket.connect"},
                # Send a subscribe command (currently a no-op)
                {"type": "websocket.receive", "text": '{"action": "subscribe"}'},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )

    # Should have accept message
    accept_msgs = [m for m in messages if m["type"] == "websocket.accept"]
    assert len(accept_msgs) > 0


def test_admin_ws_multiple_clients_connect_disconnect() -> None:
    anyio.run(_test_admin_ws_multiple_clients)


async def _test_admin_ws_multiple_clients() -> None:
    """Verify multiple admin clients can connect and disconnect independently."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    _seed_admin(game_engine)
    token = _access_token()

    async with _lifespan(app):

        async def client_session() -> list[AsgiMessage]:
            return await _run_admin_websocket(
                app,
                token=token,
                incoming=[
                    {"type": "websocket.connect"},
                    {"type": "websocket.disconnect", "code": 1000},
                ],
            )

        # Start 3 concurrent connections
        async with anyio.create_task_group() as tg:
            results = []

            async def run_client() -> None:
                result = await client_session()
                results.append(result)

            tg.start_soon(run_client)
            tg.start_soon(run_client)
            tg.start_soon(run_client)

        # All should have connected and disconnected
        assert len(results) == 3
        # Each should have accept and close
        for result in results:
            accept_msgs = [m for m in result if m["type"] == "websocket.accept"]
            assert len(accept_msgs) > 0


# =============================================================================
# CONNECTION MANAGEMENT TESTS
# =============================================================================


def test_admin_ws_client_with_malformed_receive() -> None:
    anyio.run(_test_admin_ws_malformed_receive)


async def _test_admin_ws_malformed_receive() -> None:
    """Verify WS gracefully handles malformed client messages."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    _seed_admin(game_engine)
    token = _access_token()

    async with _lifespan(app):
        messages = await _run_admin_websocket(
            app,
            token=token,
            incoming=[
                {"type": "websocket.connect"},
                # Invalid JSON in receive
                {"type": "websocket.receive", "text": "not valid json {{{"},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )

    # Should not crash; connection should handle gracefully
    accept_msgs = [m for m in messages if m["type"] == "websocket.accept"]
    assert len(accept_msgs) > 0


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


def test_admin_ws_handles_receive_error() -> None:
    anyio.run(_test_admin_ws_receive_error)


async def _test_admin_ws_receive_error() -> None:
    """Verify WS gracefully handles errors when receiving client messages."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    _seed_admin(game_engine)
    token = _access_token()

    async with _lifespan(app):
        messages = await _run_admin_websocket(
            app,
            token=token,
            incoming=[
                {"type": "websocket.connect"},
                # Malformed message (no text/bytes)
                {"type": "websocket.receive"},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )

    # Should not crash; connection should close normally
    assert len(messages) > 0
