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
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.models.audit import AuditEvent
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


def test_post_command_records_perf_breakdown_in_audit() -> None:
    anyio.run(_test_post_command_records_perf_breakdown)


async def _test_post_command_records_perf_breakdown() -> None:
    # End-to-end: a real command's COMMAND_EXECUTED audit event carries the
    # Sprint 35.3 per-operation `perf` breakdown that /analytics/performance reads.
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS,
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, _ = await _http_form_post(
            app,
            "/command",
            form={"command": "look"},
            cookies={"player_id": "player-1"},
        )

        with Session(audit_engine) as session:
            event = session.exec(
                select(AuditEvent).where(
                    AuditEvent.event_type == GameEvent.COMMAND_EXECUTED.value
                )
            ).first()

    assert status == 200
    assert event is not None
    perf = event.payload_json.get("perf")
    assert isinstance(perf, dict)
    assert set(perf) == {"command_parse", "condition_evaluate", "db_commit"}
    assert all(isinstance(value, (int, float)) for value in perf.values())


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


# ---------------------------------------------------------------------------
# Disconnect broadcast hygiene (quit): exactly one "leaves the game." and no
# spurious "connection flickers." when the WS then closes.
# ---------------------------------------------------------------------------


class _RecordingSocket:
    """An observer socket that records every pushed message."""

    def __init__(self) -> None:
        self.sent: list[Any] = []

    async def accept(self) -> None:
        pass

    async def send_json(self, data: Any) -> None:
        self.sent.append(data)


def _ws_scope(query_string: bytes) -> AsgiMessage:
    return {
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
    }


def test_quit_broadcasts_leaves_once_and_no_flicker() -> None:
    anyio.run(_test_quit_broadcasts_leaves_once_and_no_flicker)


async def _test_quit_broadcasts_leaves_once_and_no_flicker() -> None:
    """The exact reported scenario: player-1 quits while player-2 watches.

    player-2 should see 'player-1 leaves the game.' exactly once (not twice),
    and must NOT also see 'player-1's connection flickers.' when player-1's
    WebSocket subsequently closes — the graceful-quit path already tore the
    session down.
    """
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )

    async with _lifespan(app):
        state = app.state.lorecraft

        # Materialize player-1 via the dev-cookie path and learn its room.
        await _http_form_post(
            app, "/command", form={"command": "look"}, cookies={"player_id": "player-1"}
        )
        with Session(game_engine) as session:
            p1 = session.exec(select(Player).where(Player.id == "player-1")).first()
            assert p1 is not None
            room_id = p1.current_room_id
            session.add(
                Player(
                    id="observer",
                    username="observer",
                    current_room_id=room_id,
                    respawn_room_id=room_id,
                    visited_rooms=[room_id],
                )
            )
            session.commit()

        # An observer in the same room, connected with a recording socket.
        observer_socket = _RecordingSocket()
        state.manager._connections["observer"] = observer_socket  # type: ignore[assignment]
        state.manager.move_player("observer", None, room_id)

        # Drive player-1's real WebSocket, held live via a controllable stream.
        recv_tx, recv_rx = anyio.create_memory_object_stream[AsgiMessage](8)
        connected = anyio.Event()

        async def p1_receive() -> AsgiMessage:
            return await recv_rx.receive()

        async def p1_send(message: AsgiMessage) -> None:
            if message["type"] == "websocket.send":
                import json

                if json.loads(message["text"]).get("type") == "connected":
                    connected.set()

        async with anyio.create_task_group() as tg, recv_tx, recv_rx:
            tg.start_soon(app, _ws_scope(b"player_id=player-1"), p1_receive, p1_send)
            await recv_tx.send({"type": "websocket.connect"})
            with anyio.fail_after(5):
                await connected.wait()

            # player-1 quits (graceful): broadcasts "leaves the game." once and
            # removes player-1 from the manager.
            await _http_form_post(
                app,
                "/command",
                form={"command": "quit"},
                cookies={"player_id": "player-1"},
            )

            # player-1's socket now closes — the WS handler must NOT re-broadcast
            # a "connection flickers." on top of the graceful teardown.
            await recv_tx.send({"type": "websocket.disconnect", "code": 1000})

    contents = [
        str(m.get("content", "")) for m in observer_socket.sent if isinstance(m, dict)
    ]
    leaves = [c for c in contents if "leaves the game" in c]
    flickers = [c for c in contents if "connection flickers" in c]
    assert len(leaves) == 1, contents
    assert flickers == [], contents


# ---------------------------------------------------------------------------
# Crash capture (Sprint 57.3)
# ---------------------------------------------------------------------------


def test_post_command_unhandled_exception_returns_friendly_error() -> None:
    anyio.run(_test_post_command_unhandled_exception)


async def _test_post_command_unhandled_exception() -> None:
    from unittest.mock import patch

    from lorecraft.engine.models.audit import CrashReport

    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS,
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        with patch(
            "lorecraft.webui.player.frontend.broadcast_command_effects",
            side_effect=RuntimeError("boom"),
        ):
            status, html = await _http_form_post(
                app,
                "/command",
                form={"command": "look"},
                cookies={"player_id": "player-1"},
            )

        with Session(audit_engine) as session:
            crash = session.exec(select(CrashReport)).first()

    # A 500 (or a dropped connection, for the WS path) is exactly what
    # Sprint 57.3 replaces with a graceful in-game error.
    assert status == 200
    assert "went wrong" in html.lower()
    assert crash is not None
    assert crash.command_text == "look"
    assert crash.player_id == "player-1"
    assert "RuntimeError" in crash.stack_trace
    assert "boom" in crash.stack_trace
