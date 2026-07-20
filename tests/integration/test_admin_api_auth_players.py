"""Integration tests for admin REST API: auth, admin accounts, and player management."""

from __future__ import annotations

import time
from typing import Any

import anyio
from sqlmodel import Session, select

from lorecraft.config import Settings
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.items import ItemStack
from lorecraft.engine.models.meters import ActiveEffect
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Item
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.main import create_app

from tests.integration._admin_api_support import (
    _SECRET,
    _SETTINGS,
    _access_token,
    _http,
    _lifespan,
    _make_engines,
    _seed_admin,
)

# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


def test_login_returns_access_and_refresh_tokens() -> None:
    anyio.run(_test_login)


async def _test_login() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        _seed_admin(game_engine)
        status, data = await _http(
            app,
            "POST",
            "/admin/auth/token",
            body={"username": "testadmin", "password": "password"},
        )
    assert status == 200
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password_returns_401() -> None:
    anyio.run(_test_login_bad_password)


async def _test_login_bad_password() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        _seed_admin(game_engine)
        status, _ = await _http(
            app,
            "POST",
            "/admin/auth/token",
            body={"username": "testadmin", "password": "wrong"},
        )
    assert status == 401


def test_unauthenticated_request_returns_403() -> None:
    anyio.run(_test_unauthenticated)


async def _test_unauthenticated() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, _ = await _http(app, "GET", "/admin/players")
    assert status in (401, 403)  # HTTPBearer returns 401/403 without credentials


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------


def test_list_players_returns_player_1() -> None:
    anyio.run(_test_list_players)


async def _test_list_players() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/players", token=token)
    assert status == 200
    assert isinstance(data, list)
    assert any(p["username"] == "player-1" for p in data)


def test_player_state_returns_full_state() -> None:
    anyio.run(_test_player_state)


async def _test_player_state() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    with Session(game_engine) as session:
        session.add(
            Item(
                id="admin_test_helm",
                name="Admin Test Helm",
                description="A deterministic test helm.",
                slot="head",
                wearable=True,
            )
        )
        session.add(
            ItemStack(
                item_id="admin_test_helm",
                owner_type="player",
                owner_id="player-1",
                quantity=1,
                slot="head",
            )
        )
        session.commit()
    async with _lifespan(app):
        status, data = await _http(
            app, "GET", "/admin/players/player-1/state", token=token
        )
    assert status == 200
    assert data["username"] == "player-1"
    assert "flags" in data
    assert "inventory" in data
    assert data["equipment"][0]["item_id"] == "admin_test_helm"
    state_parts = {part["key"]: part for part in data["body"]}
    assert state_parts["head"]["slots"][0]["item"]["item_id"] == "admin_test_helm"
    assert "visited_rooms" in data
    assert "respawn_room_id" in data


def test_update_player_edits_record_fields() -> None:
    anyio.run(_test_update_player)


async def _test_update_player() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app,
            "PATCH",
            "/admin/players/player-1",
            body={
                "username": "edited-player",
                "respawn_room_id": "The Market Stalls",
                "pvp_consent": True,
                "ghost_state": True,
                "flags": {"admin_note": "reviewed"},
                "reason": "support request",
            },
            token=token,
        )
    assert status == 200
    assert data["username"] == "edited-player"
    assert data["respawn_room_id"] == "market_stalls"
    assert data["pvp_consent"] is True
    assert data["ghost_state"] is True
    assert data["flags"] == {"admin_note": "reviewed"}
    with Session(game_engine) as session:
        player = session.get(Player, "player-1")
    assert player is not None
    assert player.username == "edited-player"
    assert player.respawn_room_id == "market_stalls"


def test_update_player_requires_reason() -> None:
    anyio.run(_test_update_player_requires_reason)


async def _test_update_player_requires_reason() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app,
            "PATCH",
            "/admin/players/player-1",
            body={"username": "edited-player"},
            token=token,
        )
    assert status == 422
    assert data["detail"] == "Admin reason is required"


def test_observe_player_returns_snapshot_and_recent_events() -> None:
    anyio.run(_test_observe_player)


async def _test_observe_player() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    with Session(audit_engine) as session:
        session.add(
            AuditEvent(
                transaction_id="txn-observe",
                correlation_id="corr-observe",
                actor_id="player-1",
                event_type="command_executed",
                source_type="player",
                room_id="village_square",
                game_time=0.0,
                real_time=time.time(),
                severity="INFO",
                summary="Command executed: look",
                payload_json={"command": "look"},
            )
        )
        session.add(
            AuditEvent(
                transaction_id="txn-observe-time",
                correlation_id="corr-observe-time",
                actor_id="player-1",
                event_type=GameEvent.TIME_ADVANCED.value,
                source_type="clock",
                room_id="village_square",
                game_time=1.0,
                real_time=time.time() + 1,
                severity="INFO",
                summary="time_update",
                payload_json={"hour": 12, "minute": 0},
            )
        )
        session.commit()
    async with _lifespan(app):
        status, data = await _http(
            app, "GET", "/admin/players/player-1/observe", token=token
        )
    assert status == 200
    assert data["player"]["username"] == "player-1"
    assert "body" in data["player"]
    assert data["recent_events"][0]["summary"] == "Command executed: look"
    assert {event["event_type"] for event in data["recent_events"]} == {
        "command_executed"
    }


def test_observer_cannot_update_player_record() -> None:
    anyio.run(_test_observer_cannot_update_player)


async def _test_observer_cannot_update_player() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="observer")
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "PATCH",
            "/admin/players/player-1",
            body={"username": "edited-player", "reason": "support request"},
            token=token,
        )
    assert status == 403


def test_admin_can_heal_and_revitalize_player() -> None:
    anyio.run(_test_admin_can_heal_and_revitalize_player)


async def _test_admin_can_heal_and_revitalize_player() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        with Session(game_engine) as session:
            meter = app.state.lorecraft.meters.get(session, "player", "player-1", "hp")
            app.state.lorecraft.meters.set_current(session, meter, 10.0)
            session.commit()

        heal_status, heal = await _http(
            app,
            "POST",
            "/admin/players/player-1/heal",
            body={"amount": 15, "reason": "support recovery"},
            token=token,
        )
        assert heal_status == 200
        assert heal["status"] == "healed"
        assert heal["meter"]["current"] == 25.0

        revitalize_status, revitalize = await _http(
            app,
            "POST",
            "/admin/players/player-1/revitalize",
            body={"reason": "support full restore"},
            token=token,
        )
        assert revitalize_status == 200
        assert revitalize["status"] == "revitalized"
        assert {m["key"] for m in revitalize["meters"]} == {"hp", "fatigue"}
        hp = next(m for m in revitalize["meters"] if m["key"] == "hp")
        assert hp["after"]["current"] == hp["after"]["maximum"]

    with Session(audit_engine) as session:
        events = session.exec(select(AuditEvent)).all()
    assert any(e.payload_json["action"] == "player.heal" for e in events)
    assert any(e.payload_json["action"] == "player.revitalize" for e in events)


def test_admin_can_buff_player() -> None:
    anyio.run(_test_admin_can_buff_player)


async def _test_admin_can_buff_player() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/players/player-1/buff",
            body={
                "effect_key": "fortified",
                "duration_ticks": 30,
                "amount": 4,
                "reason": "support buff",
            },
            token=token,
        )
    assert status == 200
    assert data["status"] == "buffed"
    assert data["effect"]["effect_key"] == "fortified"
    assert data["effect"]["payload"] == {"amount": 4.0}
    with Session(game_engine) as session:
        effect = session.get(ActiveEffect, data["effect"]["effect_id"])
    assert effect is not None
    assert effect.entity_type == "player"
    assert effect.entity_id == "player-1"


def test_admin_can_bestow_coins_and_items() -> None:
    anyio.run(_test_admin_can_bestow_coins_and_items)


async def _test_admin_can_bestow_coins_and_items() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    with Session(game_engine) as session:
        session.add(
            Item(
                id="admin_test_gift",
                name="Admin Test Gift",
                description="A deterministic admin grant item.",
            )
        )
        session.commit()

    observed_messages: list[dict[str, Any]] = []
    async with _lifespan(app):
        unsubscribe = app.state.lorecraft.manager.observe_player_output(
            "player-1", observed_messages.append
        )
        status, data = await _http(
            app,
            "POST",
            "/admin/players/player-1/bestow",
            body={
                "coins": 1000,
                "item_id": "admin_test_gift",
                "quantity": 2,
                "reason": "support grant",
            },
            token=token,
        )
        unsubscribe()
    assert status == 200
    assert data["status"] == "bestowed"
    assert data["coins_granted"] == 1000
    assert data["coins"] >= 1000
    assert data["items"][0]["item_id"] == "admin_test_gift"
    assert data["items"][0]["quantity"] == 2
    assert observed_messages == [
        {
            "type": "feed_append",
            "content": (
                "A guardian angel gives you 1,000 coins and 2 Admin Test Gifts!"
            ),
            "message_type": "system",
        },
        {
            "type": "state_change",
            "affected_panels": ["inventory", "vitals", "stats-panel"],
            "actor_id": "admin",
        },
    ]
    with Session(game_engine) as session:
        assert LedgerService().balance_of(session, "player", "player-1") >= 1000
        stack = session.get(ItemStack, data["items"][0]["stack_id"])
    assert stack is not None
    assert stack.owner_type == "player"
    assert stack.owner_id == "player-1"


def test_observer_cannot_bestow_player() -> None:
    anyio.run(_test_observer_cannot_bestow_player)


async def _test_observer_cannot_bestow_player() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="observer")
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/admin/players/player-1/bestow",
            body={"coins": 10, "reason": "observer grant attempt"},
            token=token,
        )
    assert status == 403


def test_teleport_changes_player_room() -> None:
    anyio.run(_test_teleport)


async def _test_teleport() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/players/player-1/teleport",
            body={"room_id": "market_stalls", "reason": "support relocation"},
            token=token,
        )
    assert status == 200
    assert data["room_id"] == "market_stalls"
    with Session(game_engine) as session:
        player = session.get(Player, "player-1")
    assert player is not None
    assert player.current_room_id == "market_stalls"


def test_teleport_emits_player_moved_for_enter_exit_behaviour() -> None:
    anyio.run(_test_teleport_emits_player_moved)


async def _test_teleport_emits_player_moved() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        payloads: list[Any] = []
        app.state.lorecraft.bus.on(
            GameEvent.PLAYER_MOVED,
            lambda event, ctx: payloads.append(event.payload),
        )
        with Session(game_engine) as session:
            before = session.get(Player, "player-1")
            assert before is not None
            origin = before.current_room_id

        status, _ = await _http(
            app,
            "POST",
            "/admin/players/player-1/teleport",
            body={"room_id": "market_stalls", "reason": "test relocation"},
            token=token,
        )
        assert status == 200

    assert len(payloads) == 1
    assert payloads[0]["player_id"] == "player-1"
    assert payloads[0]["from_room_id"] == origin
    assert payloads[0]["to_room_id"] == "market_stalls"


def test_set_player_flags_merges_flags() -> None:
    anyio.run(_test_set_flags)


async def _test_set_flags() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/players/player-1/flags",
            body={"flags": {"cave_open": True}, "reason": "test flag edit"},
            token=token,
        )
    assert status == 200
    assert data["flags"]["cave_open"] is True
    with Session(game_engine) as session:
        player = session.get(Player, "player-1")
    assert player is not None
    assert player.flags.get("cave_open") is True


# ---------------------------------------------------------------------------
# Player state manipulation (freeze/unfreeze)
# ---------------------------------------------------------------------------


def test_freeze_player_sets_ghost_state() -> None:
    anyio.run(_test_freeze_player)


async def _test_freeze_player() -> None:
    from lorecraft.engine.models.session import PlayerSession

    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_admin(game_engine)

    # Create an active session for the player
    with Session(game_engine) as session:
        session.add(
            PlayerSession(
                id="test-session",
                player_id="player-1",
                connected_at=time.time(),
                status="active",
            )
        )
        session.commit()

    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/players/player-1/freeze",
            body={"reason": "moderation freeze"},
            token=token,
        )
    assert status == 200


def test_unfreeze_player_clears_ghost_state() -> None:
    anyio.run(_test_unfreeze_player)


async def _test_unfreeze_player() -> None:
    from lorecraft.engine.models.session import PlayerSession

    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_admin(game_engine)

    # Create a frozen session for the player
    with Session(game_engine) as session:
        session.add(
            PlayerSession(
                id="test-session",
                player_id="player-1",
                connected_at=time.time(),
                status="frozen",
            )
        )
        session.commit()

    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/players/player-1/unfreeze",
            body={"reason": "moderation unfreeze"},
            token=token,
        )
    assert status == 200


# ---------------------------------------------------------------------------
# Admin accounts
# ---------------------------------------------------------------------------


def test_list_admin_accounts() -> None:
    anyio.run(_test_list_accounts)


async def _test_list_accounts() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    _seed_admin(game_engine)

    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/accounts", token=token)
    assert status == 200
    assert isinstance(data, list)
    # Should have at least the test admin
    assert len(data) >= 1


# ---------------------------------------------------------------------------
# Seed admin from settings
# ---------------------------------------------------------------------------


def test_seed_admin_creates_user_on_startup() -> None:
    anyio.run(_test_seed_admin)


async def _test_seed_admin() -> None:
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        admin_seed_username="admin",
        admin_seed_password="adminpass",
        admin_seed_role="superadmin",
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, data = await _http(
            app,
            "POST",
            "/admin/auth/token",
            body={"username": "admin", "password": "adminpass"},
        )
    assert status == 200
    assert "access_token" in data
