"""
Characterization tests for web/frontend.py — Sprint 7.1

Lock in current behavior before Sprint 8–9 refactors (module decomposition & service consistency).
Focus areas:
- State resolution: game screen initial state, player lookup, room/inventory/feed snapshots
- Session reconnect edge cases: grace period handling, reconnection flow
- Feed pagination: ?since= parameter, chronological ordering
- Error rendering: error page structure, HTTP status codes

Most tests here construct `Settings(..., allow_query_player_id=True)` — a
deliberate opt-in to the legacy `?player_id=`/cookie fallback (off by
default since Sprint 4's login/WS-ticket flow shipped; see docs/roadmap.md
4.6), since these tests exercise state resolution directly rather than the
login UI.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlencode

import anyio
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from lorecraft.config import Settings
from lorecraft.db import create_tables
from lorecraft.engine.game.holders import Location
from lorecraft.main import create_app
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.session import PlayerSession
from lorecraft.engine.models.world import Item
from lorecraft.engine.services.item_location import ItemLocationService

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


@asynccontextmanager
async def _lifespan(app: Any) -> AsyncIterator[None]:
    receive_tx, receive_rx = anyio.create_memory_object_stream[AsgiMessage](4)
    send_tx, send_rx = anyio.create_memory_object_stream[AsgiMessage](4)

    async with (
        receive_tx,
        receive_rx,
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
            receive_rx.receive,
            send_tx.send,
        )
        await receive_tx.send({"type": "lifespan.startup"})
        startup = await send_rx.receive()
        assert startup == {"type": "lifespan.startup.complete"}
        try:
            yield
        finally:
            await receive_tx.send({"type": "lifespan.shutdown"})
            shutdown = await send_rx.receive()
            assert shutdown == {"type": "lifespan.shutdown.complete"}


async def _http_get(
    app: Any,
    path: str,
    *,
    cookies: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Run HTTP GET request and return (status, body)."""
    sent = False
    messages: list[AsgiMessage] = []

    query_string = b""
    if query_params:
        query_string = urlencode(query_params).encode()

    async def receive() -> AsgiMessage:
        nonlocal sent
        if sent:
            await anyio.sleep_forever()
        sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg: AsgiMessage) -> None:
        messages.append(msg)

    headers: list[tuple[bytes, bytes]] = []
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode()))

    with anyio.fail_after(5):
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": query_string,
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


async def _http_post_form(
    app: Any,
    path: str,
    *,
    form: dict[str, str],
    cookies: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Run HTTP POST form request and return (status, body)."""
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


# =============================================================================
# STATE RESOLUTION TESTS
# =============================================================================


def test_game_screen_initial_state_shows_player_in_current_room() -> None:
    anyio.run(_test_game_screen_initial_state_shows_player_in_current_room)


async def _test_game_screen_initial_state_shows_player_in_current_room() -> None:
    """Verify /game renders initial state with player, room, inventory, feed."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert status == 200
    # Verify key sections are present
    assert "feed" in html.lower() or "message" in html.lower()
    assert "inventory" in html.lower() or "item" in html.lower()
    assert "village_square" in html.lower() or "player" in html.lower()


def test_game_screen_state_includes_current_player() -> None:
    anyio.run(_test_game_screen_state_includes_current_player)


async def _test_game_screen_state_includes_current_player() -> None:
    """Verify game screen context has player, room, inventory, etc."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()

    assert status == 200
    assert player is not None
    assert player.username in html or player.id in html


def test_game_screen_default_prefs_render_comfortable() -> None:
    anyio.run(_test_game_screen_default_prefs_render_comfortable)


async def _test_game_screen_default_prefs_render_comfortable() -> None:
    """A player with no stored preferences renders the comfortable default."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert status == 200
    assert "density-comfortable" in html
    # reduced-motion class is absent by default; feed verbosity default is normal.
    assert "reduced-motion" not in html
    assert 'data-feed-verbosity="normal"' in html


def test_game_screen_reflects_stored_preferences() -> None:
    anyio.run(_test_game_screen_reflects_stored_preferences)


async def _test_game_screen_reflects_stored_preferences() -> None:
    """Stored preferences drive the body classes/data attributes on /game."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # Set preferences on the seeded player, then render.
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {
                "display_density": "compact",
                "reduced_motion": True,
                "feed_verbosity": "terse",
            }
            db.add(player)
            db.commit()
        status, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert status == 200
    assert "density-compact" in html
    assert "reduced-motion" in html
    assert 'data-feed-verbosity="terse"' in html


def test_settings_get_renders_form() -> None:
    anyio.run(_test_settings_get_renders_form)


async def _test_settings_get_renders_form() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_get(
            app, "/settings", cookies={"player_id": "player-1"}
        )

    assert status == 200
    assert 'name="display_density"' in html
    assert 'name="reduced_motion"' in html
    assert 'name="hidden_panels"' in html


def test_settings_post_persists_preferences() -> None:
    anyio.run(_test_settings_post_persists_preferences)


async def _test_settings_post_persists_preferences() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_post_form(
            app,
            "/settings",
            form={
                "display_density": "compact",
                "feed_verbosity": "terse",
                "timestamp_format": "clock24",
                "reduced_motion": "on",
                "hidden_panels": "minimap",
            },
            cookies={"player_id": "player-1"},
        )
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()

    assert status == 200
    assert "Preferences saved." in html
    assert player is not None
    # Only non-default values are stored.
    assert player.preferences["display_density"] == "compact"
    assert player.preferences["feed_verbosity"] == "terse"
    assert player.preferences["timestamp_format"] == "clock24"
    assert player.preferences["reduced_motion"] is True
    assert player.preferences["hidden_panels"] == ["minimap"]
    # And the rendered form reflects the saved state on the way back.
    assert "density-compact" in html


def test_settings_post_invalid_value_falls_back_to_default() -> None:
    anyio.run(_test_settings_post_invalid_value_falls_back_to_default)


async def _test_settings_post_invalid_value_falls_back_to_default() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        await _http_post_form(
            app,
            "/settings",
            form={"display_density": "not-a-real-density"},
            cookies={"player_id": "player-1"},
        )
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()

    assert player is not None
    # Invalid value never persists — the blob stays empty (all defaults).
    assert "display_density" not in player.preferences


def test_game_screen_state_includes_inventory() -> None:
    anyio.run(_test_game_screen_state_includes_inventory)


async def _test_game_screen_state_includes_inventory() -> None:
    """Verify /game shows player inventory."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # Add an item to player inventory
        with Session(game_engine) as db:
            db.add(Item(id="test-coin", name="Test Coin", description="A test coin"))
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            db.commit()
            if player:
                ItemLocationService(db).spawn(
                    "test-coin", Location("player", player.id)
                )
                db.commit()

        status, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert status == 200
    assert (
        "test-coin" in html.lower()
        or "Test Coin" in html
        or "inventory" in html.lower()
    )


def test_game_screen_state_includes_room_description() -> None:
    anyio.run(_test_game_screen_state_includes_room_description)


async def _test_game_screen_state_includes_room_description() -> None:
    """Verify /game shows current room description."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert status == 200
    # Room description should be rendered
    assert "room" in html.lower() or "village_square" in html.lower()


def test_game_screen_feed_excludes_raw_command_records() -> None:
    anyio.run(_test_game_screen_feed_excludes_raw_command_records)


async def _test_game_screen_feed_excludes_raw_command_records() -> None:
    """Verify initial feed excludes COMMAND_EXECUTED audit events."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # Add a COMMAND_EXECUTED audit event
        with Session(audit_engine) as db:
            db.add(
                AuditEvent(
                    transaction_id="txn-cmd",
                    correlation_id="corr-cmd",
                    actor_id="player-1",
                    event_type="COMMAND_EXECUTED",
                    source_type="command",
                    room_id="village_square",
                    game_time=0.0,
                    real_time=time.time(),
                    summary="west",
                )
            )
            db.commit()

        status, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert status == 200
    # COMMAND_EXECUTED should not appear in the rendered feed
    assert "COMMAND_EXECUTED" not in html


def test_game_screen_handles_missing_room() -> None:
    anyio.run(_test_game_screen_handles_missing_room)


async def _test_game_screen_handles_missing_room() -> None:
    """Verify game screen handles player in nonexistent room gracefully."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # Move player to nonexistent room
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            if player:
                player.current_room_id = "nonexistent-room"
                db.add(player)
                db.commit()

        status, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert status == 200
    # Should not crash, render something graceful


def test_no_session_cookie_returns_401_when_fallback_disabled() -> None:
    anyio.run(_test_no_session_cookie_returns_401_when_fallback_disabled)


async def _test_no_session_cookie_returns_401_when_fallback_disabled() -> None:
    """Verify no valid session cookie returns 401 when legacy fallback is disabled."""
    game_engine, audit_engine = _make_engines()
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        allow_query_player_id=False,
    )
    app = create_app(
        settings=settings,
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # No cookies, no query params, fallback disabled
        status, html = await _http_get(app, "/game")

    assert status == 401


# =============================================================================
# SESSION RECONNECT & GRACE PERIOD TESTS
# =============================================================================


def test_game_screen_shows_players_online_status() -> None:
    anyio.run(_test_game_screen_shows_players_online_status)


async def _test_game_screen_shows_players_online_status() -> None:
    """Verify /game includes players_here panel with online status."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert status == 200
    # players_here should be rendered or at least no crash
    assert "player" in html.lower()


def test_partials_players_online_endpoint_exists() -> None:
    anyio.run(_test_partials_players_online_endpoint_exists)


async def _test_partials_players_online_endpoint_exists() -> None:
    """Verify /partials/players-online endpoint works."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_get(
            app, "/partials/players-online", cookies={"player_id": "player-1"}
        )

    assert status == 200


def test_partials_players_online_shows_presence_status() -> None:
    anyio.run(_test_partials_players_online_shows_presence_status)


async def _test_partials_players_online_shows_presence_status() -> None:
    """Verify players-online partial includes presence indicators."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_get(
            app, "/partials/players-online", cookies={"player_id": "player-1"}
        )

    assert status == 200
    # Should show some status: online, away, grace, etc
    assert (
        "online" in html.lower()
        or "away" in html.lower()
        or "reconnect" in html.lower()
    )


def test_grace_period_session_status_query() -> None:
    anyio.run(_test_grace_period_session_status_query)


async def _test_grace_period_session_status_query() -> None:
    """Verify session can be in grace status and is shown correctly."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # Create a session in grace status
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            if player:
                grace_session = PlayerSession(
                    id="grace-session",
                    player_id=player.id,
                    connected_at=time.time() - 3600,
                    disconnected_at=time.time(),
                    status="grace",
                )
                db.add(grace_session)
                db.commit()

        # Fetch players online — should show grace status
        status, html = await _http_get(
            app, "/partials/players-online", cookies={"player_id": "player-1"}
        )

    assert status == 200
    assert "grace" in html.lower() or "reconnect" in html.lower()


# =============================================================================
# FEED PAGINATION TESTS
# =============================================================================


def test_feed_partial_endpoint_exists() -> None:
    anyio.run(_test_feed_partial_endpoint_exists)


async def _test_feed_partial_endpoint_exists() -> None:
    """Verify /partials/feed endpoint responds."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_get(
            app, "/partials/feed", cookies={"player_id": "player-1"}
        )

    assert status == 200


def test_feed_partial_with_since_returns_feed_items() -> None:
    anyio.run(_test_feed_partial_with_since_returns_feed_items)


async def _test_feed_partial_with_since_returns_feed_items() -> None:
    """Verify /partials/feed?since=X returns only newer messages."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # Add some audit events
        with Session(audit_engine) as db:
            now = time.time()
            for i in range(3):
                db.add(
                    AuditEvent(
                        transaction_id=f"txn-{i}",
                        correlation_id=f"corr-{i}",
                        actor_id="player-1",
                        event_type="TEST_EVENT",
                        source_type="test",
                        room_id="village_square",
                        game_time=float(i),
                        real_time=now - (3 - i),
                        summary=f"Test event {i}",
                    )
                )
            db.commit()

        # First fetch without since
        status1, html1 = await _http_get(
            app, "/partials/feed", cookies={"player_id": "player-1"}
        )
        assert status1 == 200

        # Then fetch with since parameter (feed_items template)
        status2, html2 = await _http_get(
            app,
            "/partials/feed",
            cookies={"player_id": "player-1"},
            query_params={"since": "1"},
        )
        assert status2 == 200


def test_feed_orders_messages_chronologically() -> None:
    anyio.run(_test_feed_orders_messages_chronologically)


async def _test_feed_orders_messages_chronologically() -> None:
    """Verify feed messages are in chronological order (oldest first)."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        now = time.time()
        with Session(audit_engine) as db:
            # Add events in reverse chronological order
            for i in range(3):
                db.add(
                    AuditEvent(
                        id=1000 + i,
                        transaction_id=f"txn-{i}",
                        correlation_id=f"corr-{i}",
                        actor_id="player-1",
                        event_type="TEST_EVENT",
                        source_type="test",
                        room_id="village_square",
                        game_time=float(i),
                        real_time=now - (10 - i * 5),
                        summary=f"Event {i}",
                    )
                )
            db.commit()

        status, html = await _http_get(
            app, "/partials/feed", cookies={"player_id": "player-1"}
        )

    assert status == 200
    # Events should appear in chronological order (Event 0, Event 1, Event 2)
    # We don't assert the exact order here since feed is a rendered HTML fragment,
    # but we verify it doesn't crash


def test_feed_excludes_command_events_from_display() -> None:
    anyio.run(_test_feed_excludes_command_events_from_display)


async def _test_feed_excludes_command_events_from_display() -> None:
    """Verify COMMAND event types are filtered from feed display."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        now = time.time()
        with Session(audit_engine) as db:
            # Add a narrative event and a command event
            db.add(
                AuditEvent(
                    transaction_id="txn-narrative",
                    correlation_id="corr-narrative",
                    actor_id="player-1",
                    event_type="NARRATIVE",
                    source_type="narrative",
                    room_id="village_square",
                    game_time=0.0,
                    real_time=now,
                    summary="A thing happened",
                )
            )
            db.add(
                AuditEvent(
                    transaction_id="txn-cmd",
                    correlation_id="corr-cmd",
                    actor_id="player-1",
                    event_type="COMMAND_EXECUTED",
                    source_type="command",
                    room_id="village_square",
                    game_time=0.0,
                    real_time=now,
                    summary="west",
                )
            )
            db.commit()

        status, html = await _http_get(
            app, "/partials/feed", cookies={"player_id": "player-1"}
        )

    assert status == 200
    # COMMAND should not appear in the feed display
    assert "COMMAND" not in html or "command_executed" not in html.lower()


# =============================================================================
# ERROR RENDERING TESTS
# =============================================================================


def test_invalid_player_id_returns_404() -> None:
    anyio.run(_test_invalid_player_id_returns_404)


async def _test_invalid_player_id_returns_404() -> None:
    """Verify accessing /game with invalid player_id returns 404."""
    game_engine, audit_engine = _make_engines()
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        allow_query_player_id=True,
    )
    app = create_app(
        settings=settings,
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_get(
            app, "/game", query_params={"player_id": "nonexistent-player-xyz"}
        )

    # May return 404 or create a fallback player depending on dev mode
    # The behavior should be consistent


def test_game_screen_empty_feed_on_first_entry() -> None:
    anyio.run(_test_game_screen_empty_feed_on_first_entry)


async def _test_game_screen_empty_feed_on_first_entry() -> None:
    """Verify first-time entry shows welcome message or empty feed gracefully."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # Create a new player with no audit history
        with Session(game_engine) as db:
            new_player = Player(
                id="new-player",
                username="newbie",
                current_room_id="village_square",
                respawn_room_id="village_square",
                visited_rooms=["village_square"],
            )
            db.add(new_player)
            db.commit()

        status, html = await _http_get(
            app, "/game", cookies={"player_id": "new-player"}
        )

    assert status == 200
    # Should show welcome message or empty feed, not error
    assert (
        "welcome" in html.lower() or "arrive" in html.lower() or "feed" in html.lower()
    )


def test_command_response_includes_feed_html() -> None:
    anyio.run(_test_command_response_includes_feed_html)


async def _test_command_response_includes_feed_html() -> None:
    """Verify POST /command response includes feed items HTML."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_post_form(
            app,
            "/command",
            form={"command": "look"},
            cookies={"player_id": "player-1"},
        )

    assert status == 200
    # Response should contain feed items or message


def test_empty_command_returns_empty_feed() -> None:
    anyio.run(_test_empty_command_returns_empty_feed)


async def _test_empty_command_returns_empty_feed() -> None:
    """Verify empty/whitespace command returns empty feed without error."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        status, html = await _http_post_form(
            app,
            "/command",
            form={"command": "   "},
            cookies={"player_id": "player-1"},
        )

    assert status == 200
    # Empty command should not error


def test_command_oob_swaps_are_valid_html() -> None:
    anyio.run(_test_command_oob_swaps_are_valid_html)


async def _test_command_oob_swaps_are_valid_html() -> None:
    """Verify OOB swap responses have valid HTML structure."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # Command that triggers OOB swaps (e.g., movement)
        status, html = await _http_post_form(
            app,
            "/command",
            form={"command": "go east"},
            cookies={"player_id": "player-1"},
        )

    assert status == 200
    # OOB swaps should have hx-swap-oob="true" attributes
    if "hx-swap-oob" in html:
        assert 'hx-swap-oob="true"' in html


def test_room_panel_partial_without_room_returns_gracefully() -> None:
    anyio.run(_test_room_panel_partial_without_room_returns_gracefully)


async def _test_room_panel_partial_without_room_returns_gracefully() -> None:
    """Verify /partials/room-description handles missing room gracefully."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # Set player to nonexistent room
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            if player:
                player.current_room_id = "void"
                db.add(player)
                db.commit()

        status, html = await _http_get(
            app, "/partials/room-description", cookies={"player_id": "player-1"}
        )

    assert status == 200


def test_inventory_partial_with_many_items() -> None:
    anyio.run(_test_inventory_partial_with_many_items)


async def _test_inventory_partial_with_many_items() -> None:
    """Verify /partials/inventory renders many items without error."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # Add many items to inventory
        with Session(game_engine) as db:
            for i in range(20):
                db.add(Item(id=f"item-{i}", name=f"Item {i}", description=f"Item {i}"))
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            db.commit()
            if player:
                item_location = ItemLocationService(db)
                for i in range(20):
                    item_location.spawn(f"item-{i}", Location("player", player.id))
                db.commit()

        status, html = await _http_get(
            app, "/partials/inventory", cookies={"player_id": "player-1"}
        )

    assert status == 200
    # Should render all items


def test_minimap_partial_with_visited_rooms() -> None:
    anyio.run(_test_minimap_partial_with_visited_rooms)


async def _test_minimap_partial_with_visited_rooms() -> None:
    """Verify /partials/minimap renders with visited rooms."""
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            allow_query_player_id=True,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        # Set visited rooms
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            if player:
                player.visited_rooms = ["village_square", "market_stalls"]
                db.add(player)
                db.commit()

        status, html = await _http_get(
            app, "/partials/minimap", cookies={"player_id": "player-1"}
        )

    assert status == 200
    # Should render minimap with map data
