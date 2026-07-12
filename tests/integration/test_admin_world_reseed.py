"""Integration tests for the admin DB wipe + reseed endpoint (Sprint 72.2).

Data-driven per AGENTS.md: the world content is fixture YAML written to a temp
file the app is pointed at, never the repo's real `world_content/world.yaml`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from lorecraft.config import Settings
from lorecraft.db import create_tables
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room
from lorecraft.main import create_app
from lorecraft.webui.admin.auth import create_token

_SECRET = "test-jwt-secret-for-reseed-tests!"

_WORLD_V1 = """
rooms:
  - id: square
    name: Square
    description: A busy square.
    map_x: 0
    map_y: 0
  - id: garden
    name: Garden
    description: A quiet garden.
    map_x: 1
    map_y: 0
"""

_WORLD_V2 = """
rooms:
  - id: square
    name: Square
    description: A busy square.
    map_x: 0
    map_y: 0
  - id: plaza
    name: Plaza
    description: A grand plaza.
    map_x: 2
    map_y: 0
"""

_MALFORMED = """
rooms:
  - id: square
    name: Square
    description: Bad exit.
    map_x: 0
    map_y: 0
    exits:
      - direction: north
        target_room_id: nowhere
"""

AsgiMessage = dict[str, Any]


def _make_engines() -> tuple[Any, Any]:
    game = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    audit = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(game_engine=game, audit_engine=audit)
    return game, audit


def _settings(world_path: Path) -> Settings:
    return Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        world_yaml_path=str(world_path),
        seed_player_start_room="square",
    )


def _token(role: str = "superadmin") -> str:
    return create_token("testadmin", role, _SECRET, 900, "access")


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


def test_reseed_wipes_and_reimports(tmp_path: Path) -> None:
    anyio.run(_reseed_happy_path, tmp_path)


async def _reseed_happy_path(tmp_path: Path) -> None:
    world = tmp_path / "world.yaml"
    world.write_text(_WORLD_V1, encoding="utf-8")
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_settings(world), game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        # Startup imported V1 (square, garden). Strand player-1 in `garden`.
        with Session(game_engine) as session:
            player = session.get(Player, "player-1")
            assert player is not None
            player.current_room_id = "garden"
            session.add(player)
            session.commit()

        # Now point the same file at V2 (square, plaza — garden dropped).
        world.write_text(_WORLD_V2, encoding="utf-8")
        status, data = await _http(
            app, "POST", "/admin/world/reseed", token=_token("superadmin")
        )

    assert status == 200, data
    assert data["status"] == "reseeded"
    assert data["rooms"] == 2
    assert data["relocated_players"] == 1

    with Session(game_engine) as session:
        room_ids = {r.id for r in session.exec(select(Room)).all()}
        assert room_ids == {"square", "plaza"}  # garden wiped, plaza added
        player = session.get(Player, "player-1")
        assert player is not None
        assert player.current_room_id == "square"  # relocated off deleted room


def test_reseed_requires_superadmin(tmp_path: Path) -> None:
    anyio.run(_reseed_auth_gated, tmp_path)


async def _reseed_auth_gated(tmp_path: Path) -> None:
    world = tmp_path / "world.yaml"
    world.write_text(_WORLD_V1, encoding="utf-8")
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_settings(world), game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        wb_status, _ = await _http(
            app, "POST", "/admin/world/reseed", token=_token("world-builder")
        )
        anon_status, _ = await _http(app, "POST", "/admin/world/reseed")

    assert wb_status == 403  # world-builder is below superadmin
    assert anon_status in (401, 403)  # no credentials

    # World left intact — the rejected calls did not wipe anything.
    with Session(game_engine) as session:
        room_ids = {r.id for r in session.exec(select(Room)).all()}
    assert room_ids == {"square", "garden"}


def test_reseed_malformed_yaml_returns_422_without_wiping(tmp_path: Path) -> None:
    anyio.run(_reseed_malformed, tmp_path)


async def _reseed_malformed(tmp_path: Path) -> None:
    world = tmp_path / "world.yaml"
    world.write_text(_WORLD_V1, encoding="utf-8")
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_settings(world), game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        world.write_text(_MALFORMED, encoding="utf-8")
        status, data = await _http(
            app, "POST", "/admin/world/reseed", token=_token("superadmin")
        )

    assert status == 422, data
    with Session(game_engine) as session:
        room_ids = {r.id for r in session.exec(select(Room)).all()}
    assert room_ids == {"square", "garden"}  # untouched — no half-apply
