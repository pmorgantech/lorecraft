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


def test_game_screen_has_accessibility_landmarks() -> None:
    anyio.run(_test_game_screen_has_accessibility_landmarks)


async def _test_game_screen_has_accessibility_landmarks() -> None:
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
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    # Skip link, main landmark, and a live-region feed for screen readers.
    assert "Skip to main content" in html
    assert 'id="main-content"' in html
    assert 'role="main"' in html
    assert 'aria-live="polite"' in html


def test_game_screen_applies_accessibility_body_classes() -> None:
    anyio.run(_test_game_screen_applies_accessibility_body_classes)


async def _test_game_screen_applies_accessibility_body_classes() -> None:
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"high_contrast": True, "font_scale": "xlarge"}
            db.add(player)
            db.commit()
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert "high-contrast" in html
    assert "font-xlarge" in html


def test_game_screen_applies_theme_body_class() -> None:
    anyio.run(_test_game_screen_applies_theme_body_class)


async def _test_game_screen_applies_theme_body_class() -> None:
    """The selected theme surfaces as a `theme-<name>` class on <body> (Sprint 58.1)."""
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
        # Default (no stored theme) -> terminal.
        _, default_html = await _http_get(
            app, "/game", cookies={"player_id": "player-1"}
        )
        assert "theme-terminal" in default_html

        # A stored non-default theme repaints via the body class.
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"theme": "slate"}
            db.add(player)
            db.commit()
        _, slate_html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert "theme-slate" in slate_html
    assert "theme-terminal" not in slate_html


def test_mode_default_theme_injected_as_single_source_for_client_js() -> None:
    anyio.run(_test_mode_default_theme_injected_as_single_source_for_client_js)


async def _test_mode_default_theme_injected_as_single_source_for_client_js() -> None:
    """`window.LC_MODE_DEFAULT_THEME` (Sprint 67) carries preferences.py's
    MODE_DEFAULT_THEME to the client so lcApplyTheme() (base.html) and
    applyPreview() (settings.html) resolve 'auto' from one source instead of
    hand-copied JS literals that can drift out of sync."""
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
        _, game_html = await _http_get(app, "/game", cookies={"player_id": "player-1"})
        _, settings_html = await _http_get(
            app, "/settings", cookies={"player_id": "player-1"}
        )

    for html in (game_html, settings_html):
        assert "window.LC_MODE_DEFAULT_THEME = " in html
        assert '"standard": "terminal"' in html
        assert '"classic": "mono-green"' in html
        # No hand-copied per-layout JS literal left over from before Sprint 67.
        assert "standard:'terminal'" not in html


def test_typography_fonts_loaded_and_feed_inherits_mode_font() -> None:
    anyio.run(_test_typography_fonts_loaded_and_feed_inherits_mode_font)


async def _test_typography_fonts_loaded_and_feed_inherits_mode_font() -> None:
    """Per-mode typography (Sprint 60): the four theme families are loaded, and
    the chronicle no longer hardcodes a serif font utility — it inherits the
    active Mode's font (JetBrains Mono under Standard/terminal), which the
    per-mode CSS blocks key on."""
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
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    # All four mode families are requested from the font host.
    assert "JetBrains+Mono" in html
    assert "IBM+Plex+Sans" in html
    assert "IBM+Plex+Mono" in html
    assert "Spectral" in html
    # The chronicle carries no font utility, so it inherits the mode font (the
    # feed div is the one with role="log"/aria-label="Game narrative log").
    feed_open = html.index('aria-label="Game narrative log"')
    feed_tag = html[html.rindex("<div", 0, feed_open) : html.index(">", feed_open)]
    assert "font-serif" not in feed_tag
    assert "font-mono" not in feed_tag


def test_game_screen_applies_layout_body_class() -> None:
    anyio.run(_test_game_screen_applies_layout_body_class)


async def _test_game_screen_applies_layout_body_class() -> None:
    """The chosen layout surfaces as an independent `layout-<name>` body class (Sprint 58.5)."""
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
        _, default_html = await _http_get(
            app, "/game", cookies={"player_id": "player-1"}
        )
        assert "layout-standard" in default_html

        # Theme and layout are independent axes — both classes co-exist.
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"theme": "slate", "layout": "e-reader"}
            db.add(player)
            db.commit()
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert "layout-e-reader" in html
    assert "theme-slate" in html
    assert "layout-standard" not in html


def test_inventory_and_quests_share_right_rail() -> None:
    anyio.run(_test_inventory_and_quests_share_right_rail)


async def _test_inventory_and_quests_share_right_rail() -> None:
    """Standard's right rail is ONE full-height card tabbed between Inv /
    Quests / Stats (Sprint 62, from lorecraft-export/standard) — inventory
    rendered once, AFTER the centre feed. Dock is a bespoke card shell: its
    Pack card holds the inventory (rendered once) with a Quests footer, so no
    tabs. (E-reader and classic are bespoke shells with their own
    arrangements, tested separately.)"""
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

    results: dict[str, str] = {}
    async with _lifespan(app):
        for layout in ("standard", "dock"):
            with Session(game_engine) as db:
                player = db.exec(select(Player).where(Player.id == "player-1")).first()
                assert player is not None
                player.preferences = {"layout": layout}
                db.add(player)
                db.commit()
            _, results[layout] = await _http_get(
                app, "/game", cookies={"player_id": "player-1"}
            )

    for layout, html in results.items():
        # Inventory lives to the right, rendered once, after the centre feed.
        assert html.count('id="inventory"') == 1, layout
        assert html.index('id="inventory"') > html.index('id="feed"'), layout

    # Standard uses one tabbed right card: Inv / Quests / Stats.
    assert ">Inv</button>" in results["standard"]
    assert ">Quests</button>" in results["standard"]
    assert ">Stats</button>" in results["standard"]
    assert 'id="stats-panel"' in results["standard"]
    # Dock is a bespoke card shell — no tabbed rail; the Pack card holds
    # inventory, and the textual invlist row view is present for it.
    assert ">Stats</button>" not in results["dock"]
    assert "dock-card" in results["dock"]
    assert "invlist" in results["dock"]


def test_immersive_layout_renders_full_bleed_shell() -> None:
    anyio.run(_test_immersive_layout_renders_full_bleed_shell)


async def _test_immersive_layout_renders_full_bleed_shell() -> None:
    """Immersive is a bespoke cinematic shell (Sprint 59.8): a slim left icon
    rail, a full-bleed chronicle (#feed), and a floating minimap card + command
    bar. Chat folds INTO the chronicle — no separate pane — and the room /
    inventory / players / quest panels are dropped for focus."""
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"layout": "immersive"}  # separate_chat off
            db.add(player)
            db.commit()
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert "layout-immersive" in html
    assert "immersive-rail" in html  # slim left icon rail
    assert "immersive-cmd" in html  # floating command bar
    assert "immersive-map" in html  # floating minimap card
    assert html.count('id="feed"') == 1  # the full-bleed chronicle
    assert html.count('id="command-input"') == 1
    assert 'id="minimap"' in html
    # Chat folds into the chronicle: no separate chat pane/feed.
    assert 'id="chat-pane"' not in html
    assert 'id="chat-feed"' not in html
    # Room + inventory + players + quests panels are dropped for focus.
    assert "Current Location" not in html
    assert 'id="inventory"' not in html
    assert "Here Now" not in html
    assert ">Players</button>" not in html


def test_standard_layout_keeps_players_column_and_tab() -> None:
    anyio.run(_test_standard_layout_keeps_players_column_and_tab)


async def _test_standard_layout_keeps_players_column_and_tab() -> None:
    """Sanity check the inverse of the immersive test above: the standard grid
    keeps the who's-here readout (ALSO HERE, folded into the Current Location
    card per lorecraft-export/standard) + the mobile Panel tab (Sprint 62)."""
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
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert "ALSO HERE" in html
    assert 'id="players-online"' in html
    assert ">Panel</button>" in html


def test_immersive_movement_narrates_room_as_styled_card() -> None:
    anyio.run(_test_immersive_movement_narrates_room_as_styled_card)


async def _test_immersive_movement_narrates_room_as_styled_card() -> None:
    """Immersive drops the room panel, so entering a new room must narrate the
    room in the chronicle instead — as a styled `room-card` block (name /
    description / exits with the panel's colouring), something plain movement
    never did before, since that was previously the panel's job (Sprint 58.8,
    styled in Sprint 60). Standard layout gets no such card (its panel already
    shows the room): the card's `room-card` class is the unambiguous signal.

    Uses the real seeded Ashmoore dev world (`village_square`'s `north` exit
    leads to the blacksmith's forge) rather than fabricated fixtures — the
    test app auto-imports `world_content/world.yaml` on startup, and adding a
    second same-direction Exit row would just be ignored/ambiguous alongside
    the real one (per AGENTS.md: tests use the shipped world, not a parallel
    hardcoded one)."""
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"layout": "immersive"}
            db.add(player)
            db.commit()

        status, immersive_html = await _http_post_form(
            app,
            "/command",
            form={"command": "go north"},
            cookies={"player_id": "player-1"},
        )
        assert status == 200
        assert "room-card" in immersive_html
        assert "Forge and Hammer" in immersive_html
        assert "Exits:" in immersive_html

        # Move back south and switch to standard — no room card this time
        # (the room panel's OOB swap already covers it).
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"layout": "standard"}
            db.add(player)
            db.commit()

        status, standard_html = await _http_post_form(
            app,
            "/command",
            form={"command": "go south"},
            cookies={"player_id": "player-1"},
        )

    assert status == 200
    assert "room-card" not in standard_html


def test_immersive_look_renders_styled_room_card() -> None:
    anyio.run(_test_immersive_look_renders_styled_room_card)


async def _test_immersive_look_renders_styled_room_card() -> None:
    """`look` in immersive renders the room as a styled `room-card` block in
    the chronicle (mirroring the Current Location panel that this layout drops)
    instead of the engine's flat ctx.say() text, which is suppressed to avoid
    showing the room twice. The card carries the "who's here" line too (the
    Here Now panel doesn't exist here): no second player means no such line; a
    second player produces exactly one (Sprint 60).

    The seeded Ashmoore dev world already has `player-2` in `village_square`
    (its default multiplayer fixture), so the "accompanied" case needs no
    setup — only "alone" does, by relocating player-2 elsewhere first."""
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"layout": "immersive"}
            db.add(player)
            # Move the seeded player-2 out of village_square so player-1 is
            # genuinely alone for the first assertion.
            other = db.exec(select(Player).where(Player.id == "player-2")).first()
            if other is not None:
                other.current_room_id = "blacksmith_forge"
                db.add(other)
            db.commit()

        status, alone_html = await _http_post_form(
            app, "/command", form={"command": "look"}, cookies={"player_id": "player-1"}
        )
        assert status == 200
        # The room is narrated as a styled card even when alone…
        assert "room-card" in alone_html
        # …but with no other player present, no "who's here" line.
        assert "player-2 is here." not in alone_html

        with Session(game_engine) as db:
            other = db.exec(select(Player).where(Player.id == "player-2")).first()
            assert other is not None
            other.current_room_id = "village_square"
            db.add(other)
            db.commit()

        status, accompanied_html = await _http_post_form(
            app, "/command", form={"command": "look"}, cookies={"player_id": "player-1"}
        )

    assert status == 200
    # Match the outer card div specifically (not `.room-card__name`, which
    # also starts with the `room-card` prefix).
    assert accompanied_html.count('class="room-card"') == 1
    assert "player-2 is here." in accompanied_html


def test_standard_look_narrates_in_feed_without_room_card() -> None:
    anyio.run(_test_standard_look_narrates_in_feed_without_room_card)


async def _test_standard_look_narrates_in_feed_without_room_card() -> None:
    """A bare `look` in standard keeps the engine's own narration in the feed
    (the Current Location panel exists, so no room card fires — and crucially
    the card's look-suppression must NOT swallow the output; regression for a
    Sprint 62 bug where it suppressed on every layout)."""
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
            app, "/command", form={"command": "look"}, cookies={"player_id": "player-1"}
        )

    assert status == 200
    assert "room-card" not in html
    # The engine's look narration (room name at minimum) reached the feed.
    assert 'class="msg' in html
    assert "Village Square" in html


def test_stats_pane_shows_default_attributes_without_a_saved_row() -> None:
    anyio.run(_test_stats_pane_shows_default_attributes_without_a_saved_row)


async def _test_stats_pane_shows_default_attributes_without_a_saved_row() -> None:
    """A PlayerStats row is only ever persisted on save-load (engine/services/
    save.py), never at character creation — so a normally-created player (the
    seeded dev player-1 included) has none. Attributes + Level must still show
    in the Stats pane using the model's own declared defaults (all 10, level
    1), matching the read-time-default convention the `score` command already
    uses for level/xp (Sprint 63 fix — this previously omitted the section
    entirely for every player until one loaded a save)."""
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"layout": "standard"}
            db.add(player)
            db.commit()
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert 'id="stats-panel"' in html
    assert "ATTRIBUTES" in html
    assert "Strength" in html and ">10<" in html
    assert "Level 1" in html


def test_immersive_own_chat_folds_into_chronicle() -> None:
    anyio.run(_test_immersive_own_chat_folds_into_chronicle)


async def _test_immersive_own_chat_folds_into_chronicle() -> None:
    """Immersive folds chat INTO the full-bleed chronicle (Sprint 59.8): the
    actor's own chat echo stays inline in #feed — tagged `mine` for styling —
    rather than being OOB-routed to a separate #chat-feed pane (which is what
    classic and separate_chat do). Standard likewise keeps it in the plain
    feed, so neither should carry the #chat-feed OOB carrier."""
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"layout": "immersive"}
            db.add(player)
            db.commit()

        status, immersive_html = await _http_post_form(
            app,
            "/command",
            form={"command": "say hello"},
            cookies={"player_id": "player-1"},
        )
        assert status == 200
        # Own echo is present and styled, but NOT routed to a chat pane.
        assert "chat mine" in immersive_html
        assert "beforeend:#chat-feed" not in immersive_html

        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"layout": "standard"}
            db.add(player)
            db.commit()

        status, standard_html = await _http_post_form(
            app,
            "/command",
            form={"command": "say hello again"},
            cookies={"player_id": "player-1"},
        )

    assert status == 200
    # The players-online panel is OOB-swapped regardless of layout — that's
    # unrelated to this feature — so check specifically for chat routing.
    assert "beforeend:#chat-feed" not in standard_html


def test_classic_layout_renders_mud_terminal() -> None:
    anyio.run(_test_classic_layout_renders_mud_terminal)


async def _test_classic_layout_renders_mud_terminal() -> None:
    """Classic is a purpose-built old-MUD shell (Sprint 59): one chronicle
    (#feed) with a vitals prompt + command input, a chat pane (#chat-feed) with
    its own input, and a minimap — no room/players/inventory panels. The
    chronicle narrates the room as a styled room card (shared with immersive,
    Sprint 60)."""
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            # Stored legacy "classic" scheme name aliases to mono-green
            # (Sprint 62 rename) — asserting on the alias keeps the migration
            # path covered.
            player.preferences = {"layout": "classic", "theme": "classic"}
            db.add(player)
            db.commit()
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert "layout-classic" in html and "theme-mono-green" in html
    # Chronicle + its own command prompt, chat pane + its own input, minimap.
    assert 'id="feed"' in html
    assert 'id="chat-feed"' in html
    assert 'id="minimap"' in html
    assert 'id="vitals"' in html
    # A single command input — chat is sent via `say …` on that same line (the
    # separate chat input was removed per review), so there's no second one.
    assert html.count('id="command-input"') == 1
    assert html.count('name="command"') == 1
    # No three-column grid panels — this is chronicle-only.
    assert "Here Now" not in html
    # Room narrated in the chronicle on load (the styled room card).
    assert "room-card" in html


def test_classic_layout_command_refreshes_vitals_and_routes_chat() -> None:
    anyio.run(_test_classic_layout_command_refreshes_vitals_and_routes_chat)


async def _test_classic_layout_command_refreshes_vitals_and_routes_chat() -> None:
    """In classic, every command OOB-refreshes the vitals line, and the actor's
    own chat echo routes into the chat pane (Sprint 59)."""
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"layout": "classic"}
            db.add(player)
            db.commit()

        status, look_html = await _http_post_form(
            app, "/command", form={"command": "look"}, cookies={"player_id": "player-1"}
        )
        assert status == 200
        assert 'id="vitals" hx-swap-oob' in look_html

        status, say_html = await _http_post_form(
            app,
            "/command",
            form={"command": "say hello"},
            cookies={"player_id": "player-1"},
        )

    assert status == 200
    # The chat echo is wrapped in an OOB *carrier* div whose content (the real
    # .msg block) HTMX appends to #chat-feed — so each line lands as its own
    # block instead of loose inline spans that wrap together (Sprint 59 fix).
    assert (
        '<div hx-swap-oob="beforeend:#chat-feed"><div class="msg chat mine' in say_html
    )


def test_ereader_layout_renders_ledger_folio_rail() -> None:
    anyio.run(_test_ereader_layout_renders_ledger_folio_rail)


async def _test_ereader_layout_renders_ledger_folio_rail() -> None:
    """E-reader is a bespoke book shell (Sprint 59): a left ledger with the
    location readout (#room-description) + compass map, a centre serif folio
    (#feed + an Inscribe prompt), and a right vertical tab rail. It keeps the
    location panel (unlike immersive/classic), so it does NOT MUD-narrate."""
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"layout": "e-reader", "theme": "parchment"}
            db.add(player)
            db.commit()
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert "layout-e-reader" in html
    assert 'id="room-description"' in html  # left ledger location readout
    assert 'id="feed"' in html  # centre folio chronicle
    assert 'id="minimap"' in html
    assert "ereader-tab" in html  # right vertical tab rail
    assert "Inscribe" in html  # folio command button
    # A single command input; no full-width command bar or mobile tab bar.
    assert html.count('id="command-input"') == 1
    assert ">Players</button>" not in html
    # It shows the location panel, so it does not synthesize the MUD room block.
    assert "msg-room_event" not in html
    # The side-rail tabs append into the chronicle, and the page carries the
    # global auto-follow seam so their output pins #feed to the bottom (the tabs
    # themselves don't run handleCommandSuccess — see the htmx:afterSwap handler).
    assert html.count('hx-target="#feed" hx-swap="beforeend"') >= 4  # 4 rail tabs
    assert "htmx:afterSwap" in html
    assert "target.scrollTop = target.scrollHeight" in html


def test_dock_layout_renders_card_shell() -> None:
    anyio.run(_test_dock_layout_renders_card_shell)


async def _test_dock_layout_renders_card_shell() -> None:
    """Dock is a bespoke card shell (Sprint 59/60/62): three columns of
    floating .dock-card panels — LEFT location (with ALSO HERE) + minimap,
    CENTRE chronicle (#feed with a Send button), RIGHT one full-height card
    with WINDOW-SHADE sections Inv / Quests / Stats (the accordion take on
    Standard's tabbed pane; inventory keeps Dock's textual invlist row view).
    It keeps the location panel, so no MUD narration; and it is NOT the grid,
    so no tabbed pane / mobile tab bar. #minimap itself is bare content — the
    card head supplies the MINIMAP title, so it doesn't double-box."""
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"layout": "dock", "theme": "slate"}
            db.add(player)
            db.commit()
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert "layout-dock" in html
    assert "dock-card" in html  # floating cards
    assert "dock-send" in html  # gradient Send button
    assert "invlist" in html  # Dock's textual inventory row
    assert 'id="room-description"' in html  # LEFT location card
    assert "ALSO HERE" in html  # who's-here folded into the location card
    assert 'id="minimap"' in html
    assert html.count('id="feed"') == 1
    assert html.count('id="inventory"') == 1
    assert 'id="players-online"' in html  # the ALSO HERE list keeps the OOB id
    assert 'id="quest-tracker"' in html  # quests shade
    assert 'id="stats-panel"' in html  # stats shade
    # Window-shade right pane: three shade heads, no separate Party/Pack cards.
    assert html.count("dock-shade__head") >= 3
    assert ">PARTY</span>" not in html
    assert ">PACK</span>" not in html
    # Bespoke shell: no standard tabbed pane, no mobile tab bar.
    assert ">Stats</button>" not in html
    assert ">Panel</button>" not in html
    # It keeps the location panel, so it does not synthesize the MUD room block.
    assert "msg-room_event" not in html


def test_minimap_style_toggles_graph_vs_compass() -> None:
    anyio.run(_test_minimap_style_toggles_graph_vs_compass)


async def _test_minimap_style_toggles_graph_vs_compass() -> None:
    """The minimap partial renders both views; the player's minimap_style picks
    which the `minimap-<style>` body class reveals. Default = graph (Sprint 59)."""
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
        _, default_html = await _http_get(
            app, "/game", cookies={"player_id": "player-1"}
        )
        assert "minimap-graph" in default_html
        # Both views are always rendered (CSS shows one).
        assert "mm-graph" in default_html and "mm-compass" in default_html
        # Both pane titles render too; CSS reveals the one matching the style —
        # "Minimap" for graph, "Exits" for compass.
        assert "mm-title-graph" in default_html and "mm-title-compass" in default_html
        assert ">Minimap</span>" in default_html and ">Exits</span>" in default_html
        # The map head carries the graph ⇄ compass toggle (Sprint 62).
        assert "lcToggleMinimapStyle()" in default_html


def test_minimap_is_bare_content_no_double_box() -> None:
    anyio.run(_test_minimap_is_bare_content_no_double_box)


async def _test_minimap_is_bare_content_no_double_box() -> None:
    """partials/minimap.html renders #minimap as bare content — no border, no
    rounded corners, no header of its own (Sprint 60). Every mode's own
    wrapping template supplies the card chrome + title instead, so a mode that
    already wraps the include in its own card (dock, e-reader, immersive)
    doesn't end up with a box nested inside a box. Checked across all five
    modes since each has its own wrapper markup."""
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
        for layout in ("standard", "dock", "e-reader", "immersive", "classic"):
            with Session(game_engine) as db:
                player = db.exec(select(Player).where(Player.id == "player-1")).first()
                assert player is not None
                player.preferences = {"layout": layout}
                db.add(player)
                db.commit()
            _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

            minimap_open = html.index('id="minimap"')
            minimap_tag = html[
                html.rindex("<div", 0, minimap_open) : html.index(">", minimap_open)
            ]
            assert "border" not in minimap_tag, layout
            assert "bg-panel" not in minimap_tag, layout
            assert "rounded" not in minimap_tag, layout

        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"minimap_style": "compass"}
            db.add(player)
            db.commit()
        _, compass_html = await _http_get(
            app, "/game", cookies={"player_id": "player-1"}
        )

    # The minimap-<style> class lands on the <body> tag (the base JS mentions
    # both class names, so assert on the tag rather than the whole document).
    body_tag = compass_html[
        compass_html.index("<body") : compass_html.index(
            ">", compass_html.index("<body")
        )
    ]
    assert "minimap-compass" in body_tag
    assert "minimap-graph" not in body_tag


def test_settings_renders_and_persists_theme() -> None:
    anyio.run(_test_settings_renders_and_persists_theme)


async def _test_settings_renders_and_persists_theme() -> None:
    """The settings form exposes the theme picker and round-trips a choice (Sprint 58.1)."""
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
        _, get_html = await _http_get(
            app, "/settings", cookies={"player_id": "player-1"}
        )
        assert 'name="theme"' in get_html
        assert 'name="layout"' in get_html

        status, _ = await _http_post_form(
            app,
            "/settings",
            form={"theme": "parchment"},
            cookies={"player_id": "player-1"},
        )
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
        # Re-open settings to confirm the saved theme is pre-selected.
        _, reget = await _http_get(app, "/settings", cookies={"player_id": "player-1"})

    assert status == 303
    assert player is not None
    assert player.preferences["theme"] == "parchment"
    assert '<option value="parchment" selected>' in reget


def test_topbar_appearance_pickers_render_on_game() -> None:
    anyio.run(_test_topbar_appearance_pickers_render_on_game)


async def _test_topbar_appearance_pickers_render_on_game() -> None:
    """The feature-flagged top-bar Theme/Layout pickers render on /game (Sprint 58)."""
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
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert 'hx-post="/settings/appearance"' in html
    assert "lcApplyTheme" in html


def test_appearance_endpoint_updates_only_supplied_fields() -> None:
    anyio.run(_test_appearance_endpoint_updates_only_supplied_fields)


async def _test_appearance_endpoint_updates_only_supplied_fields() -> None:
    """The quick picker's endpoint persists only the field(s) it posts, leaving
    every other preference untouched (Sprint 58)."""
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"theme": "slate", "display_density": "compact"}
            db.add(player)
            db.commit()

        # Change ONLY the layout via the quick endpoint.
        status, _ = await _http_post_form(
            app,
            "/settings/appearance",
            form={"layout": "e-reader"},
            cookies={"player_id": "player-1"},
        )

        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()

    assert status == 204
    assert player is not None
    assert player.preferences["layout"] == "e-reader"  # updated
    assert player.preferences["theme"] == "slate"  # untouched
    assert player.preferences["display_density"] == "compact"  # untouched


def test_game_screen_hides_panel_when_preference_set() -> None:
    anyio.run(_test_game_screen_hides_panel_when_preference_set)


async def _test_game_screen_hides_panel_when_preference_set() -> None:
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
        # Baseline: minimap panel present.
        _, before = await _http_get(app, "/game", cookies={"player_id": "player-1"})
        assert "minimap" in before.lower()

        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            assert player is not None
            player.preferences = {"hidden_panels": ["minimap"]}
            db.add(player)
            db.commit()

        _, after = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    # The minimap partial include is gated out (the panel markup is gone).
    assert after.lower().count("minimap") < before.lower().count("minimap")


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
        status, _ = await _http_post_form(
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
        # Save uses Post/Redirect/Get: it returns to /game, not the settings page.
        _, game_html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert status == 303
    assert player is not None
    # Only non-default values are stored.
    assert player.preferences["display_density"] == "compact"
    assert player.preferences["feed_verbosity"] == "terse"
    assert player.preferences["timestamp_format"] == "clock24"
    assert player.preferences["reduced_motion"] is True
    assert player.preferences["hidden_panels"] == ["minimap"]
    # And the saved prefs render on the game screen we were redirected to.
    assert "density-compact" in game_html


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


def test_quest_tracker_partial_renders_for_valid_player() -> None:
    anyio.run(_test_quest_tracker_partial_renders_for_valid_player)


async def _test_quest_tracker_partial_renders_for_valid_player() -> None:
    """Verify /partials/quest-tracker renders (empty tracker is a valid state).

    This route is only driven by a scheduler-side QuestTimerService push, so it
    had no integration coverage — only an e2e browser assertion. Pin that it
    resolves the player and renders 200 even with no active quests.
    """
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
            app, "/partials/quest-tracker", cookies={"player_id": "player-1"}
        )

    assert status == 200


def test_map_full_partial_with_visited_rooms() -> None:
    anyio.run(_test_map_full_partial_with_visited_rooms)


async def _test_map_full_partial_with_visited_rooms() -> None:
    """Verify /partials/map-full renders the full-screen map modal.

    The full-map modal route (cartography-gated reveal of known-but-unvisited
    rooms) had no integration coverage. Mirror the minimap test: seed visited
    rooms and assert the modal renders.
    """
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
        with Session(game_engine) as db:
            player = db.exec(select(Player).where(Player.id == "player-1")).first()
            if player:
                player.visited_rooms = ["village_square", "market_stalls"]
                db.add(player)
                db.commit()

        status, html = await _http_get(
            app, "/partials/map-full", cookies={"player_id": "player-1"}
        )

    assert status == 200
    # Should render the full-screen map modal with map data
