"""Integration tests for admin REST API."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import anyio
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from lorecraft.admin.auth import create_token, hash_password
from lorecraft.config import Settings
from lorecraft.main import create_app
from lorecraft.models.admin import AdminUser
from lorecraft.models.player import Player
from lorecraft.models.world import Room

_SECRET = "test-jwt-secret-for-admin-tests!"
_SETTINGS = Settings(
    database_path=":memory:",
    audit_database_path=":memory:",
    admin_jwt_secret=_SECRET,
)

AsgiMessage = dict[str, Any]


def _make_engines() -> tuple[Any, Any]:
    game = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    audit = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    return game, audit


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


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


def test_login_returns_access_and_refresh_tokens() -> None:
    anyio.run(_test_login)


async def _test_login() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        _seed_admin(game_engine)
        status, data = await _http(
            app,
            "POST",
            "/admin/auth/token",
            body={"username": "testadmin", "password": "password"},
        )
    assert status == 200
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password_returns_401() -> None:
    anyio.run(_test_login_bad_password)


async def _test_login_bad_password() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        _seed_admin(game_engine)
        status, _ = await _http(
            app,
            "POST",
            "/admin/auth/token",
            body={"username": "testadmin", "password": "wrong"},
        )
    assert status == 401


def test_unauthenticated_request_returns_403() -> None:
    anyio.run(_test_unauthenticated)


async def _test_unauthenticated() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, _ = await _http(app, "GET", "/admin/players")
    assert status in (401, 403)  # HTTPBearer returns 401/403 without credentials


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------


def test_list_players_returns_player_1() -> None:
    anyio.run(_test_list_players)


async def _test_list_players() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/players", token=token)
    assert status == 200
    assert isinstance(data, list)
    assert any(p["username"] == "player-1" for p in data)


def test_player_state_returns_full_state() -> None:
    anyio.run(_test_player_state)


async def _test_player_state() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app, "GET", "/admin/players/player-1/state", token=token
        )
    assert status == 200
    assert data["username"] == "player-1"
    assert "flags" in data
    assert "inventory" in data
    assert "visited_rooms" in data


def test_teleport_changes_player_room() -> None:
    anyio.run(_test_teleport)


async def _test_teleport() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/players/player-1/teleport",
            body={"room_id": "square"},
            token=token,
        )
    assert status == 200
    assert data["room_id"] == "square"
    with Session(game_engine) as session:
        player = session.get(Player, "player-1")
    assert player is not None
    assert player.current_room_id == "square"


def test_set_player_flags_merges_flags() -> None:
    anyio.run(_test_set_flags)


async def _test_set_flags() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/players/player-1/flags",
            body={"flags": {"cave_open": True}},
            token=token,
        )
    assert status == 200
    assert data["flags"]["cave_open"] is True
    with Session(game_engine) as session:
        player = session.get(Player, "player-1")
    assert player is not None
    assert player.flags.get("cave_open") is True


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_audit_log_returns_list() -> None:
    anyio.run(_test_audit_log)


async def _test_audit_log() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/audit", token=token)
    assert status == 200
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# World — rooms
# ---------------------------------------------------------------------------


def test_list_rooms_returns_starter_rooms() -> None:
    anyio.run(_test_list_rooms)


async def _test_list_rooms() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/world/rooms", token=token)
    assert status == 200
    assert isinstance(data, list)
    room_ids = {r["id"] for r in data}
    assert "tavern" in room_ids


def test_update_room_changes_name() -> None:
    anyio.run(_test_update_room)


async def _test_update_room() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        # Get current version first
        _, rooms = await _http(app, "GET", "/admin/world/rooms", token=token)
        tavern = next(r for r in rooms if r["id"] == "tavern")
        status, data = await _http(
            app,
            "PUT",
            "/admin/world/rooms/tavern",
            body={"name": "The Golden Flagon", "version": tavern["version"]},
            token=token,
        )
    assert status == 200
    with Session(game_engine) as session:
        room = session.get(Room, "tavern")
    assert room is not None
    assert room.name == "The Golden Flagon"
    assert room.version == tavern["version"] + 1


def test_update_room_version_conflict_returns_409() -> None:
    anyio.run(_test_version_conflict)


async def _test_version_conflict() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "PUT",
            "/admin/world/rooms/tavern",
            body={"name": "Fake", "version": 999},
            token=token,
        )
    assert status == 409


# ---------------------------------------------------------------------------
# Role enforcement
# ---------------------------------------------------------------------------


def test_observer_cannot_edit_rooms() -> None:
    anyio.run(_test_observer_cannot_edit)


async def _test_observer_cannot_edit() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token("observer")
    async with _lifespan(app):
        _, rooms = await _http(app, "GET", "/admin/world/rooms", token=token)
        tavern = next(r for r in rooms if r["id"] == "tavern")
        status, _ = await _http(
            app,
            "PUT",
            "/admin/world/rooms/tavern",
            body={"name": "X", "version": tavern["version"]},
            token=token,
        )
    assert status == 403


def test_observer_cannot_pause_clock() -> None:
    anyio.run(_test_observer_cannot_pause)


async def _test_observer_cannot_pause() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token("observer")
    async with _lifespan(app):
        status, _ = await _http(app, "POST", "/admin/clock/pause", token=token)
    assert status == 403


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


def test_get_clock_returns_current_state() -> None:
    anyio.run(_test_get_clock)


async def _test_get_clock() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/clock", token=token)
    assert status == 200
    assert "current_hour" in data
    assert "weather" in data
    assert "paused" in data


def test_pause_and_resume_clock() -> None:
    anyio.run(_test_pause_resume)


async def _test_pause_resume() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, _ = await _http(app, "POST", "/admin/clock/pause", token=token)
        assert status == 200
        _, clock = await _http(app, "GET", "/admin/clock", token=token)
        assert clock["paused"] is True

        status, _ = await _http(app, "POST", "/admin/clock/resume", token=token)
        assert status == 200
        _, clock = await _http(app, "GET", "/admin/clock", token=token)
        assert clock["paused"] is False


def test_set_weather_updates_clock() -> None:
    anyio.run(_test_set_weather)


async def _test_set_weather() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/admin/clock/weather",
            body={"weather": "blizzard"},
            token=token,
        )
        assert status == 200
        _, clock = await _http(app, "GET", "/admin/clock", token=token)
    assert clock["weather"] == "blizzard"


# ---------------------------------------------------------------------------
# Seed admin from settings
# ---------------------------------------------------------------------------


def test_seed_admin_creates_user_on_startup() -> None:
    anyio.run(_test_seed_admin)


async def _test_seed_admin() -> None:
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        admin_seed_username="admin",
        admin_seed_password="adminpass",
        admin_seed_role="superadmin",
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/auth/token",
            body={"username": "admin", "password": "adminpass"},
        )
    assert status == 200
    assert "access_token" in data
