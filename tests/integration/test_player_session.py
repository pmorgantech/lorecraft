"""Integration tests for signed player session cookies (Sprint A)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlencode

import anyio
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from lorecraft.config import Settings
from lorecraft.main import create_app
from lorecraft.models.player import Player
from lorecraft.web.player_auth import PLAYER_SESSION_COOKIE

AsgiMessage = dict[str, Any]

_SETTINGS = Settings(database_path=":memory:", audit_database_path=":memory:")
_SETTINGS_NO_LEGACY = Settings(
    database_path=":memory:",
    audit_database_path=":memory:",
    allow_query_player_id=False,
)


def _make_engines() -> tuple[Any, Any]:
    game = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    audit = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
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
            shutdown = await send_rx.receive()
            assert shutdown == {"type": "lifespan.shutdown.complete"}


async def _request(
    app: Any,
    method: str,
    path: str,
    *,
    form: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> tuple[int, list[tuple[bytes, bytes]], str]:
    messages: list[AsgiMessage] = []
    body = urlencode(form).encode() if form is not None else b""
    sent = False

    async def receive() -> AsgiMessage:
        nonlocal sent
        if sent:
            await anyio.sleep_forever()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(msg: AsgiMessage) -> None:
        messages.append(msg)

    headers: list[tuple[bytes, bytes]] = []
    if form is not None:
        headers.append((b"content-type", b"application/x-www-form-urlencoded"))
        headers.append((b"content-length", str(len(body)).encode()))
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode()))

    with anyio.fail_after(5):
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "method": method,
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
    resp_headers = next(
        m["headers"] for m in messages if m["type"] == "http.response.start"
    )
    body_bytes = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return status, resp_headers, body_bytes.decode()


def _cookie_value(headers: list[tuple[bytes, bytes]], name: str) -> str | None:
    for key, value in headers:
        if key.lower() != b"set-cookie":
            continue
        text = value.decode()
        if text.startswith(f"{name}="):
            return text.split(";", 1)[0].split("=", 1)[1]
    return None


def test_create_character_happy_path() -> None:
    anyio.run(_test_create_character_happy_path)


async def _test_create_character_happy_path() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )

    async with _lifespan(app):
        status, headers, _ = await _request(
            app,
            "POST",
            "/lobby/create",
            form={"username": "Ashen_Wanderer", "password": "hunter2"},
        )
        assert status == 303
        session_cookie = _cookie_value(headers, PLAYER_SESSION_COOKIE)
        assert session_cookie is not None

        with Session(game_engine) as session:
            player = session.exec(
                select(Player).where(Player.username == "Ashen_Wanderer")
            ).first()
        assert player is not None
        assert player.current_room_id == "village_square"

        # The minted cookie should resolve back to this exact player on /game.
        game_status, _, game_html = await _request(
            app, "GET", "/game", cookies={PLAYER_SESSION_COOKIE: session_cookie}
        )
        assert game_status == 200
        assert "Ashen_Wanderer" in game_html


def test_create_character_with_wrong_password_for_existing_username_is_rejected() -> (
    None
):
    """/lobby/create shares login_or_register() with /lobby/enter: a repeat
    username is treated as a login attempt, not a hard 'name taken' error —
    it only fails if the password doesn't match."""
    anyio.run(_test_create_character_with_wrong_password_for_existing_username)


async def _test_create_character_with_wrong_password_for_existing_username() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )

    async with _lifespan(app):
        await _request(
            app,
            "POST",
            "/lobby/create",
            form={"username": "Dup", "password": "correct-pw"},
        )
        status, _, _ = await _request(
            app,
            "POST",
            "/lobby/create",
            form={"username": "Dup", "password": "wrong-pw"},
        )

    assert status == 401


def test_create_character_with_matching_password_logs_in_existing_player() -> None:
    anyio.run(_test_create_character_with_matching_password_logs_in_existing_player)


async def _test_create_character_with_matching_password_logs_in_existing_player() -> (
    None
):
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )

    async with _lifespan(app):
        first_status, first_headers, _ = await _request(
            app,
            "POST",
            "/lobby/create",
            form={"username": "Repeat", "password": "same-pw"},
        )
        second_status, second_headers, _ = await _request(
            app,
            "POST",
            "/lobby/create",
            form={"username": "Repeat", "password": "same-pw"},
        )

    assert first_status == 303
    assert second_status == 303
    first_cookie = _cookie_value(first_headers, PLAYER_SESSION_COOKIE)
    second_cookie = _cookie_value(second_headers, PLAYER_SESSION_COOKIE)
    assert first_cookie is not None
    assert second_cookie is not None


def test_create_character_rejects_invalid_username() -> None:
    anyio.run(_test_create_character_rejects_invalid_username)


async def _test_create_character_rejects_invalid_username() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )

    async with _lifespan(app):
        status, _, _ = await _request(
            app, "POST", "/lobby/create", form={"username": "ab", "password": "pw"}
        )
        assert status == 400

        status, _, _ = await _request(
            app,
            "POST",
            "/lobby/create",
            form={"username": "has a space", "password": "pw"},
        )
        assert status == 400


def test_enter_world_rejects_unknown_player() -> None:
    anyio.run(_test_enter_world_rejects_unknown_player)


async def _test_enter_world_rejects_unknown_player() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )

    async with _lifespan(app):
        status, _, _ = await _request(
            app,
            "POST",
            "/lobby/enter",
            form={"username": "does_not_exist", "password": "whatever"},
        )

    assert status == 404


def test_forged_session_cookie_does_not_grant_identity() -> None:
    anyio.run(_test_forged_session_cookie_does_not_grant_identity)


async def _test_forged_session_cookie_does_not_grant_identity() -> None:
    """A tampered/garbage session cookie must not resolve to an arbitrary player."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )

    async with _lifespan(app):
        status, _, html = await _request(
            app,
            "GET",
            "/game",
            cookies={PLAYER_SESSION_COOKIE: "not-a-real-token"},
        )

    # allow_query_player_id defaults off since Sprint 4 (docs/roadmap.md
    # 4.6), so an invalid cookie with no legacy fallback available is a
    # hard 401 — not a silent fallback to a dev/test player.
    assert status == 401
    assert "not-a-real-token" not in html


def test_allow_query_player_id_disabled_requires_signed_session() -> None:
    anyio.run(_test_allow_query_player_id_disabled_requires_signed_session)


async def _test_allow_query_player_id_disabled_requires_signed_session() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS_NO_LEGACY, game_engine=game_engine, audit_engine=audit_engine
    )

    async with _lifespan(app):
        status, _, _ = await _request(app, "GET", "/game")
        assert status == 401

        status, _, _ = await _request(
            app, "GET", "/game", cookies={"player_id": "player-1"}
        )
        assert status == 401

        # A properly created + logged-in character still works.
        create_status, headers, _ = await _request(
            app,
            "POST",
            "/lobby/create",
            form={"username": "Signed_Only", "password": "hunter2"},
        )
        assert create_status == 303
        session_cookie = _cookie_value(headers, PLAYER_SESSION_COOKIE)
        assert session_cookie is not None

        status, _, html = await _request(
            app, "GET", "/game", cookies={PLAYER_SESSION_COOKIE: session_cookie}
        )
        assert status == 200
        assert "Signed_Only" in html


def test_lobby_page_is_reachable_with_no_session_at_all() -> None:
    """GET /lobby must not require a session — it's where one is created.

    Regression test: with allow_query_player_id defaulting off (Sprint
    4.6), a naive Depends(get_current_player) on the lobby route would
    401 a brand-new visitor before they could ever log in.
    """
    anyio.run(_test_lobby_page_is_reachable_with_no_session_at_all)


async def _test_lobby_page_is_reachable_with_no_session_at_all() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )

    async with _lifespan(app):
        status, _, html = await _request(app, "GET", "/lobby")

    assert status == 200
    assert "Log In" in html
    assert "Create New Character" in html
