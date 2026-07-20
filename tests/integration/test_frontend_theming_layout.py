"""
Characterization tests for web/frontend.py — Sprint 7.1 (theming & layout slice)

Lock in current behavior before refactors touch it. This module covers the game-screen
initial-state/preference/accessibility/theme rendering, typography, the five layout
variants (immersive/standard/classic/e-reader/dock), minimap style toggling, and the
settings render/persist/appearance endpoints.

Most tests here construct `Settings(..., allow_query_player_id=True)` — a
deliberate opt-in to the legacy `?player_id=`/cookie fallback (off by
default since Sprint 4's login/WS-ticket flow shipped; see docs/project/roadmap.md
4.6), since these tests exercise state resolution directly rather than the
login UI.
"""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.config import Settings
from lorecraft.engine.models.player import Player
from lorecraft.main import create_app

import anyio

from tests.integration._frontend_characterization_support import (
    _http_get,
    _http_post_form,
    _lifespan,
    _make_engines,
)

# =============================================================================
# STATE RESOLUTION TESTS (theming / layout)
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
    assert 'class="mobile-minimap-card flex-none hidden lg:block"' in html


def test_standard_separate_chat_is_mobile_cloaked_by_default() -> None:
    anyio.run(_test_standard_separate_chat_is_mobile_cloaked_by_default)


async def _test_standard_separate_chat_is_mobile_cloaked_by_default() -> None:
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
            player.preferences = {"separate_chat": True}
            db.add(player)
            db.commit()
        _, html = await _http_get(app, "/game", cookies={"player_id": "player-1"})

    assert 'id="chat-pane"' in html
    assert "x-cloak" in html.split('id="chat-pane"', 1)[1].split(">", 1)[0]


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
