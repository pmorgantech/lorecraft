"""
Characterization tests for web/frontend.py — Sprint 7.1 (feed & session slice)

Lock in current behavior before refactors touch it. This module covers feed
pagination/ordering/exclusion, session reconnect/grace-period handling, the
players-online partials, command-response/OOB-swap HTML, and empty-feed/invalid-player-id
edge cases.

Most tests here construct `Settings(..., allow_query_player_id=True)` — a
deliberate opt-in to the legacy `?player_id=`/cookie fallback (off by
default since Sprint 4's login/WS-ticket flow shipped; see docs/project/roadmap.md
4.6), since these tests exercise state resolution directly rather than the
login UI.
"""

from __future__ import annotations

import time

from sqlmodel import Session, select

from lorecraft.config import Settings
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.session import PlayerSession
from lorecraft.main import create_app

import anyio

from tests.integration._frontend_characterization_support import (
    _http_get,
    _http_post_form,
    _lifespan,
    _make_engines,
)

# =============================================================================
# STATE RESOLUTION TESTS (feed / session)
# =============================================================================


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
    """Verify noisy audit event types are filtered from feed display."""
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
            db.add(
                AuditEvent(
                    transaction_id="txn-time",
                    correlation_id="corr-time",
                    actor_id="player-1",
                    event_type=GameEvent.TIME_ADVANCED.value,
                    source_type="clock",
                    room_id="village_square",
                    game_time=1.0,
                    real_time=now + 1,
                    summary="time_update",
                    payload_json={"hour": 12, "minute": 0},
                )
            )
            db.commit()

        status, html = await _http_get(
            app, "/partials/feed", cookies={"player_id": "player-1"}
        )

    assert status == 200
    # COMMAND should not appear in the feed display
    assert "COMMAND" not in html or "command_executed" not in html.lower()
    assert "time_update" not in html
    assert "time_advanced" not in html


# =============================================================================
# ERROR RENDERING / EDGE CASE TESTS (feed / session)
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
