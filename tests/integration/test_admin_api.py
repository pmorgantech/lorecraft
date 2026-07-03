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
    from lorecraft.db import create_tables

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
            body={"room_id": "market_stalls"},
            token=token,
        )
    assert status == 200
    assert data["room_id"] == "market_stalls"
    with Session(game_engine) as session:
        player = session.get(Player, "player-1")
    assert player is not None
    assert player.current_room_id == "market_stalls"


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
    assert "village_square" in room_ids


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
        inn = next(r for r in rooms if r["id"] == "wandering_crow_inn")
        status, data = await _http(
            app,
            "PUT",
            "/admin/world/rooms/wandering_crow_inn",
            body={"name": "The Golden Flagon", "version": inn["version"]},
            token=token,
        )
    assert status == 200
    with Session(game_engine) as session:
        room = session.get(Room, "wandering_crow_inn")
    assert room is not None
    assert room.name == "The Golden Flagon"
    assert room.version == inn["version"] + 1


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
            "/admin/world/rooms/wandering_crow_inn",
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
        inn = next(r for r in rooms if r["id"] == "wandering_crow_inn")
        status, _ = await _http(
            app,
            "PUT",
            "/admin/world/rooms/wandering_crow_inn",
            body={"name": "X", "version": inn["version"]},
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
# Player state manipulation (freeze/unfreeze)
# ---------------------------------------------------------------------------


def test_freeze_player_sets_ghost_state() -> None:
    anyio.run(_test_freeze_player)


async def _test_freeze_player() -> None:
    from lorecraft.models.session import PlayerSession

    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_admin(game_engine)

    # Create an active session for the player
    with Session(game_engine) as session:
        session.add(
            PlayerSession(
                id="test-session",
                player_id="player-1",
                connected_at=time.time(),
                status="active",
            )
        )
        session.commit()

    async with _lifespan(app):
        status, data = await _http(
            app, "POST", "/admin/players/player-1/freeze", token=token
        )
    assert status == 200


def test_unfreeze_player_clears_ghost_state() -> None:
    anyio.run(_test_unfreeze_player)


async def _test_unfreeze_player() -> None:
    from lorecraft.models.session import PlayerSession

    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_admin(game_engine)

    # Create a frozen session for the player
    with Session(game_engine) as session:
        session.add(
            PlayerSession(
                id="test-session",
                player_id="player-1",
                connected_at=time.time(),
                status="frozen",
            )
        )
        session.commit()

    async with _lifespan(app):
        status, data = await _http(
            app, "POST", "/admin/players/player-1/unfreeze", token=token
        )
    assert status == 200


# ---------------------------------------------------------------------------
# World data (items, NPCs)
# ---------------------------------------------------------------------------


def test_list_items_returns_items() -> None:
    anyio.run(_test_list_items)


async def _test_list_items() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_admin(game_engine)

    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/world/items", token=token)
    assert status == 200
    assert isinstance(data, list)


def test_list_npcs_returns_npcs() -> None:
    anyio.run(_test_list_npcs)


async def _test_list_npcs() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_admin(game_engine)

    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/world/npcs", token=token)
    assert status == 200
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Clock management (time ratio)
# ---------------------------------------------------------------------------


def test_set_clock_time_ratio() -> None:
    anyio.run(_test_set_time_ratio)


async def _test_set_time_ratio() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_admin(game_engine)

    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/admin/clock/time-ratio",
            body={"ratio": 2.0},
            token=token,
        )
    assert status == 200


# ---------------------------------------------------------------------------
# Admin accounts
# ---------------------------------------------------------------------------


def test_list_admin_accounts() -> None:
    anyio.run(_test_list_accounts)


async def _test_list_accounts() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_admin(game_engine)

    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/accounts", token=token)
    assert status == 200
    assert isinstance(data, list)
    # Should have at least the test admin
    assert len(data) >= 1


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


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


def test_create_and_list_issues(tmp_path) -> None:
    anyio.run(_test_create_and_list_issues, tmp_path)


async def _test_create_and_list_issues(tmp_path) -> None:
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        issues_yaml_path=str(tmp_path / "issues.yaml"),
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="moderator")
    async with _lifespan(app):
        _seed_admin(game_engine, role="moderator")
        status, created = await _http(
            app,
            "POST",
            "/admin/issues",
            body={
                "title": "Movement race condition",
                "type": "bug",
                "priority": "high",
            },
            token=token,
        )
        assert status == 200
        assert created["title"] == "Movement race condition"
        assert created["status"] == "open"
        assert created["created_by"] == "testadmin"

        status, listed = await _http(app, "GET", "/admin/issues", token=token)
        assert status == 200
        assert any(i["id"] == created["id"] for i in listed)

    # Admin mutation re-exports the YAML mirror to disk.
    assert (tmp_path / "issues.yaml").is_file()


def test_update_issue_status(tmp_path) -> None:
    anyio.run(_test_update_issue_status, tmp_path)


async def _test_update_issue_status(tmp_path) -> None:
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        issues_yaml_path=str(tmp_path / "issues.yaml"),
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="moderator")
    async with _lifespan(app):
        _seed_admin(game_engine, role="moderator")
        _, created = await _http(
            app, "POST", "/admin/issues", body={"title": "Fix it"}, token=token
        )
        status, updated = await _http(
            app,
            "PUT",
            f"/admin/issues/{created['id']}",
            body={"status": "resolved"},
            token=token,
        )
        assert status == 200
        assert updated["status"] == "resolved"

        status, missing = await _http(
            app,
            "PUT",
            "/admin/issues/does-not-exist",
            body={"status": "open"},
            token=token,
        )
        assert status == 404


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------


def test_create_list_and_delete_news(tmp_path) -> None:
    anyio.run(_test_create_list_and_delete_news, tmp_path)


async def _test_create_list_and_delete_news(tmp_path) -> None:
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        news_yaml_path=str(tmp_path / "news.yaml"),
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="moderator")
    async with _lifespan(app):
        _seed_admin(game_engine, role="moderator")
        status, created = await _http(
            app,
            "POST",
            "/admin/news",
            body={"title": "Welcome to Ashmoore", "type": "server", "body": "Hello!"},
            token=token,
        )
        assert status == 200
        assert created["title"] == "Welcome to Ashmoore"
        assert created["author"] == "testadmin"

        status, listed = await _http(app, "GET", "/admin/news", token=token)
        assert status == 200
        assert any(n["id"] == created["id"] for n in listed)

        status, feed = await _http(app, "GET", "/api/news")
        assert status == 200
        assert any(n["id"] == created["id"] for n in feed)

        status, _ = await _http(
            app, "DELETE", f"/admin/news/{created['id']}", token=token
        )
        assert status == 200

        status, listed_after = await _http(app, "GET", "/admin/news", token=token)
        assert status == 200
        assert not any(n["id"] == created["id"] for n in listed_after)

    assert (tmp_path / "news.yaml").is_file()


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def test_analytics_endpoints_return_empty_lists_with_no_data() -> None:
    anyio.run(_test_analytics_endpoints_empty)


async def _test_analytics_endpoints_empty() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        for path in (
            "/admin/analytics/commands",
            "/admin/analytics/npcs",
            "/admin/analytics/quests",
            "/admin/analytics/player-hours",
        ):
            status, data = await _http(app, "GET", path, token=token)
            assert status == 200
            assert data == []


def test_analytics_latency_returns_zeroed_percentiles_with_no_data() -> None:
    anyio.run(_test_analytics_latency_empty)


async def _test_analytics_latency_empty() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/analytics/latency", token=token)
        assert status == 200
        assert data == {"p50": 0.0, "p95": 0.0, "p99": 0.0, "count": 0}


def test_analytics_invalid_range_returns_400() -> None:
    anyio.run(_test_analytics_invalid_range)


async def _test_analytics_invalid_range() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app, "GET", "/admin/analytics/commands?range=notarange", token=token
        )
        assert status == 400
        assert "detail" in data
