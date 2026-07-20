"""Integration tests for admin REST API: world content (rooms/items/npcs, clock/weather,
progression, combat ruleset, and economy region config)."""

from __future__ import annotations

from typing import Any

import anyio
from sqlmodel import Session

from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.models.world import NPC, Item, Room
from lorecraft.main import create_app

from tests.integration._admin_api_support import (
    _SETTINGS,
    _access_token,
    _http,
    _lifespan,
    _make_engines,
    _seed_admin,
)

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


def test_list_rooms_includes_map_z() -> None:
    anyio.run(_test_list_rooms_includes_map_z)


async def _test_list_rooms_includes_map_z() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/world/rooms", token=token)
    assert status == 200
    square = next(r for r in data if r["id"] == "village_square")
    assert square["map_z"] == 0


def test_update_room_changes_map_z() -> None:
    anyio.run(_test_update_room_map_z)


async def _test_update_room_map_z() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _, rooms = await _http(app, "GET", "/admin/world/rooms", token=token)
        inn = next(r for r in rooms if r["id"] == "wandering_crow_inn")
        status, _data = await _http(
            app,
            "PUT",
            "/admin/world/rooms/wandering_crow_inn",
            body={"map_z": -1, "version": inn["version"]},
            token=token,
        )
    assert status == 200
    with Session(game_engine) as session:
        room = session.get(Room, "wandering_crow_inn")
    assert room is not None
    assert room.map_z == -1


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
    assert "zone_weather" in data
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


def test_set_zone_weather_updates_climate_state() -> None:
    anyio.run(_test_set_zone_weather)


async def _test_set_zone_weather() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _, before = await _http(app, "GET", "/admin/clock", token=token)
        assert "whisperwood" in before["zone_weather"]

        status, data = await _http(
            app,
            "POST",
            "/admin/clock/zone-weather",
            body={"zone": "whisperwood", "weather": "fog"},
            token=token,
        )
        assert status == 200
        assert data == {"zone": "whisperwood", "weather": "fog"}
        _, clock = await _http(app, "GET", "/admin/clock", token=token)

    assert clock["zone_weather"]["whisperwood"] == "fog"


def test_set_zone_weather_rejects_unknown_zone() -> None:
    anyio.run(_test_set_zone_weather_unknown_zone)


async def _test_set_zone_weather_unknown_zone() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/admin/clock/zone-weather",
            body={"zone": "moon", "weather": "fog"},
            token=token,
        )

    assert status == 404


def test_set_weather_emits_weather_changed_for_narration() -> None:
    anyio.run(_test_set_weather_emits_event)


async def _test_set_weather_emits_event() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        payloads: list[Any] = []
        app.state.lorecraft.bus.on(
            GameEvent.WEATHER_CHANGED,
            lambda event, ctx: payloads.append(event.payload),
        )
        _, clock = await _http(app, "GET", "/admin/clock", token=token)
        before = clock["weather"]
        target = "blizzard" if before != "blizzard" else "clear"

        status, _ = await _http(
            app, "POST", "/admin/clock/weather", body={"weather": target}, token=token
        )
        assert status == 200
        # Re-setting the same weather must stay silent (no non-event announcement).
        status, _ = await _http(
            app, "POST", "/admin/clock/weather", body={"weather": target}, token=token
        )
        assert status == 200

    assert len(payloads) == 1
    assert payloads[0]["weather"] == target
    assert payloads[0]["previous_weather"] == before


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


def test_world_builder_can_create_and_update_items() -> None:
    anyio.run(_test_world_builder_can_create_and_update_items)


async def _test_world_builder_can_create_and_update_items() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="world-builder")
    _seed_admin(game_engine, role="world-builder")

    create_body = {
        "id": "admin_test_lantern",
        "name": "Admin Test Lantern",
        "description": "A lantern created from the admin item editor.",
        "takeable": True,
        "tradeable": True,
        "bound": False,
        "aliases": ["lamp"],
        "usable_with": ["flint"],
        "loot_table": {"common": [{"item_id": "wick", "quantity": 1}]},
        "slot": "off_hand",
        "wearable": False,
        "weight": 1.5,
        "quality": "fine",
        "max_durability": 20,
        "light": 2,
        "capacity": None,
        "effects": [{"type": "warmth", "amount": 1}],
        "value": 12,
        "category": "supplies",
        "mechanism_states": [],
        "mechanism_side_effects": {},
        "combination_side_effects": {"flint": {"set_flags": ["lantern_lit"]}},
        "context_commands": {"polish": {"say": "It gleams."}},
    }

    async with _lifespan(app):
        create_status, created = await _http(
            app, "POST", "/admin/world/items", body=create_body, token=token
        )
        duplicate_status, duplicate = await _http(
            app, "POST", "/admin/world/items", body=create_body, token=token
        )
        update_status, updated = await _http(
            app,
            "PUT",
            "/admin/world/items/admin_test_lantern",
            body={
                "name": "Updated Lantern",
                "description": "Updated by the admin item editor.",
                "slot": None,
                "max_durability": None,
                "capacity": 2.5,
                "aliases": ["lamp", "light"],
                "context_commands": {},
            },
            token=token,
        )
        with Session(game_engine) as session:
            item = session.get(Item, "admin_test_lantern")

    assert create_status == 200
    assert created["status"] == "created"
    assert created["id"] == "admin_test_lantern"
    assert created["aliases"] == ["lamp"]
    assert created["context_commands"] == {"polish": {"say": "It gleams."}}
    assert duplicate_status == 409
    assert "already exists" in duplicate["detail"]
    assert update_status == 200
    assert updated["status"] == "updated"
    assert updated["name"] == "Updated Lantern"
    assert updated["slot"] is None
    assert updated["max_durability"] is None
    assert updated["capacity"] == 2.5
    assert updated["aliases"] == ["lamp", "light"]
    assert updated["context_commands"] == {}
    assert item is not None
    assert item.name == "Updated Lantern"
    assert item.slot is None
    assert item.max_durability is None
    assert item.capacity == 2.5


def test_observer_cannot_create_items() -> None:
    anyio.run(_test_observer_cannot_create_items)


async def _test_observer_cannot_create_items() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="observer")
    _seed_admin(game_engine, role="observer")

    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/world/items",
            body={
                "id": "observer_item",
                "name": "Observer Item",
                "description": "Should not be created.",
            },
            token=token,
        )

    assert status == 403
    assert data["detail"] == "Requires world-builder role"


def test_list_npcs_returns_npcs() -> None:
    anyio.run(_test_list_npcs)


async def _test_list_npcs() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_admin(game_engine)
    with Session(game_engine) as session:
        session.add(
            Room(
                id="village_square",
                name="Village Square",
                description="A test square.",
                map_x=0,
                map_y=0,
            )
        )
        session.add(
            NPC(
                id="cogsworth",
                name="Cogsworth",
                description="A test automaton.",
                current_room_id="village_square",
                home_room_id="village_square",
                dialogue_tree_id="cogsworth_intro",
                behavior="friendly",
                max_hp=42,
                ai={"mode": "wander", "move_every": 3},
                schedule=[{"hour": 8, "action": "open_shop"}],
                context_commands={"wind": {"say": "Cogsworth winds the key."}},
                triggers=[
                    {"on": "player_entered", "do": [{"set_flags": ["met_cogsworth"]}]}
                ],
            )
        )
        session.commit()

    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/world/npcs", token=token)
    assert status == 200
    assert data[0]["id"] == "cogsworth"
    assert data[0]["current_room_name"] == "Village Square"
    assert data[0]["ai"] == {"mode": "wander", "move_every": 3}
    assert data[0]["schedule_count"] == 1
    assert data[0]["trigger_count"] == 1
    assert data[0]["context_commands"] == ["wind"]


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
# Progression config (live admin tuning)
# ---------------------------------------------------------------------------


def _seed_progression(game_engine: Any) -> None:
    from lorecraft.features.progression.models import ProgressionConfig

    with Session(game_engine) as session:
        session.add(
            ProgressionConfig(
                base=100, step=50, coins_per_level=25, skill_points_per_level=1
            )
        )
        session.commit()


def test_get_progression_config_returns_current_state() -> None:
    anyio.run(_test_get_progression)


async def _test_get_progression() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_progression(game_engine)
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/progression/config", token=token)
    assert status == 200
    assert data == {
        "base": 100,
        "step": 50,
        "coins_per_level": 25,
        "skill_points_per_level": 1,
    }


def test_post_progression_config_updates_live() -> None:
    anyio.run(_test_post_progression)


async def _test_post_progression() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_progression(game_engine)
    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/progression/config",
            body={"coins_per_level": 99, "base": 200},
            token=token,
        )
        assert status == 200
        assert data["coins_per_level"] == 99
        assert data["base"] == 200

        # A follow-up GET reflects the live change (other fields untouched).
        _, after = await _http(app, "GET", "/admin/progression/config", token=token)
    assert after["coins_per_level"] == 99
    assert after["base"] == 200
    assert after["step"] == 50
    assert after["skill_points_per_level"] == 1


def test_post_progression_config_rejects_nonpositive_base() -> None:
    anyio.run(_test_post_progression_rejects_base)


async def _test_post_progression_rejects_base() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_progression(game_engine)
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/admin/progression/config",
            body={"base": 0},
            token=token,
        )
    assert status == 422


def test_observer_cannot_edit_progression_config() -> None:
    anyio.run(_test_observer_cannot_edit_progression)


async def _test_observer_cannot_edit_progression() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token("observer")
    _seed_progression(game_engine)
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/admin/progression/config",
            body={"coins_per_level": 5},
            token=token,
        )
    assert status == 403


# ---------------------------------------------------------------------------
# Combat ruleset config (live admin tuning, Sprint 87)
# ---------------------------------------------------------------------------


def test_get_combat_rulesets_returns_known_action_rulesets() -> None:
    anyio.run(_test_get_combat_rulesets)


async def _test_get_combat_rulesets() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/combat/rulesets", token=token)

    assert status == 200
    assert data == [
        {
            "id": "core",
            "damage_multiplier": 1.0,
            "stamina_cost_multiplier": 1.0,
        }
    ]


def test_post_combat_ruleset_updates_live_config() -> None:
    anyio.run(_test_post_combat_ruleset)


async def _test_post_combat_ruleset() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/combat/rulesets/core",
            body={"damage_multiplier": 1.25, "stamina_cost_multiplier": 0.8},
            token=token,
        )
        assert status == 200
        assert data["damage_multiplier"] == 1.25
        assert data["stamina_cost_multiplier"] == 0.8

        _, after = await _http(app, "GET", "/admin/combat/rulesets", token=token)

    assert after[0]["id"] == "core"
    assert after[0]["damage_multiplier"] == 1.25
    assert after[0]["stamina_cost_multiplier"] == 0.8


def test_post_combat_ruleset_rejects_nonpositive_multiplier() -> None:
    anyio.run(_test_post_combat_ruleset_rejects_multiplier)


async def _test_post_combat_ruleset_rejects_multiplier() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/admin/combat/rulesets/core",
            body={"damage_multiplier": 0},
            token=token,
        )
    assert status == 422


def test_post_combat_ruleset_rejects_unknown_ruleset() -> None:
    anyio.run(_test_post_combat_ruleset_rejects_unknown)


async def _test_post_combat_ruleset_rejects_unknown() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/admin/combat/rulesets/missing",
            body={"damage_multiplier": 1.1},
            token=token,
        )
    assert status == 404


def test_observer_cannot_edit_combat_ruleset() -> None:
    anyio.run(_test_observer_cannot_edit_combat_ruleset)


async def _test_observer_cannot_edit_combat_ruleset() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token("observer")
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/admin/combat/rulesets/core",
            body={"damage_multiplier": 1.1},
            token=token,
        )
    assert status == 403


# ---------------------------------------------------------------------------
# Economy region pricing (live admin tuning, Sprint 76)
# ---------------------------------------------------------------------------


# Seeded AFTER lifespan startup (world bootstrap seeds its own RegionPricing rows
# from world_content/world.yaml on startup); these test zones use unique ids so
# they never collide with real world content.
def _seed_regions(game_engine: Any) -> None:
    from lorecraft.features.economy.models import RegionPricing

    with Session(game_engine) as session:
        session.add(
            RegionPricing(zone="test_zone_a", region_mult=0.9, bias={"gem": 2.0})
        )
        session.add(RegionPricing(zone="test_zone_b", region_mult=1.2, bias={}))
        session.commit()


def test_get_economy_regions_returns_all() -> None:
    anyio.run(_test_get_economy_regions)


async def _test_get_economy_regions() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _seed_regions(game_engine)
        status, data = await _http(app, "GET", "/admin/economy/regions", token=token)
    assert status == 200
    assert isinstance(data, list)
    by_zone = {r["zone"]: r for r in data}
    assert by_zone["test_zone_a"] == {
        "zone": "test_zone_a",
        "region_mult": 0.9,
        "bias": {"gem": 2.0},
    }
    assert by_zone["test_zone_b"] == {
        "zone": "test_zone_b",
        "region_mult": 1.2,
        "bias": {},
    }
    # zone-ordered
    zones = [r["zone"] for r in data]
    assert zones == sorted(zones)


def test_get_economy_regions_requires_observer() -> None:
    anyio.run(_test_get_economy_regions_requires_auth)


async def _test_get_economy_regions_requires_auth() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, _ = await _http(app, "GET", "/admin/economy/regions")
    # HTTPBearer returns 401/403 without credentials.
    assert status in (401, 403)


def test_post_economy_region_updates_mult_live() -> None:
    anyio.run(_test_post_economy_region_mult)


async def _test_post_economy_region_mult() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _seed_regions(game_engine)
        status, data = await _http(
            app,
            "POST",
            "/admin/economy/regions/test_zone_a",
            body={"region_mult": 1.5},
            token=token,
        )
        assert status == 200
        assert data["region_mult"] == 1.5
        # bias untouched when only region_mult is provided.
        assert data["bias"] == {"gem": 2.0}

        _, after = await _http(app, "GET", "/admin/economy/regions", token=token)
    zone_a = next(r for r in after if r["zone"] == "test_zone_a")
    assert zone_a["region_mult"] == 1.5
    assert zone_a["bias"] == {"gem": 2.0}


def test_post_economy_region_replaces_bias_wholesale() -> None:
    anyio.run(_test_post_economy_region_bias)


async def _test_post_economy_region_bias() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _seed_regions(game_engine)
        status, data = await _http(
            app,
            "POST",
            "/admin/economy/regions/test_zone_a",
            body={"bias": {"salt_sack": 0.5}},
            token=token,
        )
        assert status == 200
        # Wholesale replace: the old "gem" key is gone.
        assert data["bias"] == {"salt_sack": 0.5}
        # region_mult untouched when only bias is provided.
        assert data["region_mult"] == 0.9

        _, after = await _http(app, "GET", "/admin/economy/regions", token=token)
    zone_a = next(r for r in after if r["zone"] == "test_zone_a")
    assert zone_a["bias"] == {"salt_sack": 0.5}


def test_post_economy_region_unknown_zone_returns_404() -> None:
    anyio.run(_test_post_economy_region_unknown)


async def _test_post_economy_region_unknown() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _seed_regions(game_engine)
        status, _ = await _http(
            app,
            "POST",
            "/admin/economy/regions/nowhere_zone",
            body={"region_mult": 1.1},
            token=token,
        )
    assert status == 404


def test_post_economy_region_rejects_nonpositive_mult() -> None:
    anyio.run(_test_post_economy_region_bad_mult)


async def _test_post_economy_region_bad_mult() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _seed_regions(game_engine)
        status, _ = await _http(
            app,
            "POST",
            "/admin/economy/regions/test_zone_a",
            body={"region_mult": 0},
            token=token,
        )
    assert status == 422


def test_post_economy_region_rejects_nonnumeric_bias() -> None:
    anyio.run(_test_post_economy_region_bad_bias)


async def _test_post_economy_region_bad_bias() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _seed_regions(game_engine)
        status, _ = await _http(
            app,
            "POST",
            "/admin/economy/regions/test_zone_a",
            body={"bias": {"gem": "abc"}},
            token=token,
        )
    assert status == 422


def test_observer_cannot_edit_economy_region() -> None:
    anyio.run(_test_observer_cannot_edit_economy)


async def _test_observer_cannot_edit_economy() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token("observer")
    async with _lifespan(app):
        _seed_regions(game_engine)
        status, _ = await _http(
            app,
            "POST",
            "/admin/economy/regions/test_zone_a",
            body={"region_mult": 1.5},
            token=token,
        )
    assert status == 403
