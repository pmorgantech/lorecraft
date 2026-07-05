"""Integration tests for the HTMX POST /command path."""

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
from lorecraft.engine.models.player import Player
from lorecraft.engine.repos.stack_repo import StackRepo

AsgiMessage = dict[str, Any]

# allow_query_player_id=True: these tests exercise the command-dispatch
# protocol directly via ?player_id=/cookie, not the login UI added in
# Sprint 4 (see docs/roadmap.md 4.6) — a deliberate opt-in, not an oversight.
_SETTINGS = Settings(
    database_path=":memory:",
    audit_database_path=":memory:",
    allow_query_player_id=True,
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


async def _http_form_post(
    app: Any,
    path: str,
    *,
    form: dict[str, str],
    cookies: dict[str, str] | None = None,
) -> tuple[int, str]:
    sent = False
    messages: list[AsgiMessage] = []
    body = urlencode(form).encode()

    async def receive() -> AsgiMessage:
        nonlocal sent
        if sent:
            await anyio.sleep_forever()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(msg: AsgiMessage) -> None:
        messages.append(msg)

    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/x-www-form-urlencoded"),
        (b"content-length", str(len(body)).encode()),
    ]
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode()))

    with anyio.fail_after(5):
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "method": "POST",
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
    return status, body_bytes.decode()


def test_post_command_moves_player_east() -> None:
    anyio.run(_test_post_command_moves_player_east)


async def _test_post_command_moves_player_east() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS,
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_form_post(
            app,
            "/command",
            form={"command": "go east"},
            cookies={"player_id": "player-1"},
        )

        with Session(game_engine) as session:
            player = session.exec(select(Player).where(Player.id == "player-1")).first()

    assert status == 200
    assert player is not None
    assert player.current_room_id == "market_stalls"
    assert "go east" in html.lower() or "You go east" in html


def test_post_command_takes_item() -> None:
    anyio.run(_test_post_command_takes_item)


async def _test_post_command_takes_item() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS,
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_form_post(
            app,
            "/command",
            form={"command": "take coin"},
            cookies={"player_id": "player-1"},
        )

        with Session(game_engine) as session:
            player = session.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            carried = [
                stack.item_id
                for stack in StackRepo(session).stacks_for_owner("player", player.id)
            ]

    assert status == 200
    assert player is not None
    assert "copper_coin" in carried
    assert "coin" in html.lower() or "Copper" in html


def test_post_command_starts_dialogue() -> None:
    anyio.run(_test_post_command_starts_dialogue)


async def _test_post_command_starts_dialogue() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS,
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        await _http_form_post(
            app,
            "/command",
            form={"command": "go west"},
            cookies={"player_id": "player-1"},
        )
        status, html = await _http_form_post(
            app,
            "/command",
            form={"command": "talk mira"},
            cookies={"player_id": "player-1"},
        )

    assert status == 200
    assert "dialogue-overlay" in html
    assert "Mira" in html
    assert "choice" in html.lower() or "hx-vals" in html


def test_post_command_choice_advances_dialogue() -> None:
    anyio.run(_test_post_command_choice_advances_dialogue)


async def _test_post_command_choice_advances_dialogue() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS,
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        await _http_form_post(
            app,
            "/command",
            form={"command": "go west"},
            cookies={"player_id": "player-1"},
        )
        await _http_form_post(
            app,
            "/command",
            form={"command": "talk mira"},
            cookies={"player_id": "player-1"},
        )
        status, html = await _http_form_post(
            app,
            "/command",
            form={"command": "choice 1"},
            cookies={"player_id": "player-1"},
        )

    assert status == 200
    assert "Enter the number of your choice" not in html
    assert "dialogue-overlay" in html
    assert "market stalls" in html.lower() or "strange lights" in html.lower()


def test_post_command_numeric_choice_during_dialogue() -> None:
    anyio.run(_test_post_command_numeric_choice_during_dialogue)


async def _test_post_command_numeric_choice_during_dialogue() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS,
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        await _http_form_post(
            app,
            "/command",
            form={"command": "go west"},
            cookies={"player_id": "player-1"},
        )
        await _http_form_post(
            app,
            "/command",
            form={"command": "talk mira"},
            cookies={"player_id": "player-1"},
        )
        status, html = await _http_form_post(
            app,
            "/command",
            form={"command": "2"},
            cookies={"player_id": "player-1"},
        )

    assert status == 200
    assert "I don't understand that command" not in html
    assert "Enter the number of your choice" not in html


def test_post_command_shows_farewell_node_in_dialogue() -> None:
    anyio.run(_test_post_command_shows_farewell_node_in_dialogue)


async def _test_post_command_shows_farewell_node_in_dialogue() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS,
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        await _http_form_post(
            app,
            "/command",
            form={"command": "go west"},
            cookies={"player_id": "player-1"},
        )
        await _http_form_post(
            app,
            "/command",
            form={"command": "talk mira"},
            cookies={"player_id": "player-1"},
        )
        await _http_form_post(
            app,
            "/command",
            form={"command": "choice 1"},
            cookies={"player_id": "player-1"},
        )
        status, html = await _http_form_post(
            app,
            "/command",
            form={"command": "choice 1"},
            cookies={"player_id": "player-1"},
        )

    assert status == 200
    assert "Be careful out there" in html
    assert 'id="dialogue-overlay" hx-swap-oob="true"' in html
    assert "dialogue-overlay hidden" not in html


def test_post_command_bye_closes_dialogue_overlay() -> None:
    anyio.run(_test_post_command_bye_closes_dialogue_overlay)


async def _test_post_command_bye_closes_dialogue_overlay() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS,
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        await _http_form_post(
            app,
            "/command",
            form={"command": "go west"},
            cookies={"player_id": "player-1"},
        )
        await _http_form_post(
            app,
            "/command",
            form={"command": "talk mira"},
            cookies={"player_id": "player-1"},
        )
        status, html = await _http_form_post(
            app,
            "/command",
            form={"command": "bye"},
            cookies={"player_id": "player-1"},
        )

    assert status == 200
    assert "Farewell" in html
    assert 'id="dialogue-overlay" hx-swap-oob="true"' in html
    assert "dialogue-overlay flex" not in html
    assert "dialogue-overlay hidden" in html
