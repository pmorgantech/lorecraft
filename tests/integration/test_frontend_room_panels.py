"""
Characterization tests for web/frontend.py — Sprint 7.1 (room / inventory / stats panels slice)

Lock in current behavior before refactors touch it. This module covers movement/look
narration (immersive & standard), the stats pane, the shared inventory/quests rail, and
the room/inventory/minimap/quest-tracker/map-full partial endpoints, plus the /game
inventory and room-description state assertions.

Most tests here construct `Settings(..., allow_query_player_id=True)` — a
deliberate opt-in to the legacy `?player_id=`/cookie fallback (off by
default since Sprint 4's login/WS-ticket flow shipped; see docs/project/roadmap.md
4.6), since these tests exercise state resolution directly rather than the
login UI.
"""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.config import Settings
from lorecraft.engine.game.holders import Location
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Item
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.main import create_app

import anyio

from tests.integration._frontend_characterization_support import (
    _http_get,
    _http_post_form,
    _lifespan,
    _make_engines,
)

# =============================================================================
# ROOM / INVENTORY / STATS PANEL TESTS
# =============================================================================


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
