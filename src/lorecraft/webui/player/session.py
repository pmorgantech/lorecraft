"""
Lorecraft Web Session Management

Player session handling, state management, and dependency injection for the web UI.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request
from sqlmodel import Session as DBSession

from lorecraft.db import create_audit_engine, create_game_engine
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.features.items.rules import register_item_rules
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.features.quests.repo import QuestRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.services.save import SessionSafetyService
from lorecraft.state import AppState
from lorecraft.types import JsonObject
from lorecraft.webui.player.player_auth import (
    PLAYER_SESSION_COOKIE,
    create_player_token,
)

log = logging.getLogger(__name__)

# Lazily created engines (in real app these come from lifespan state)
_game_engine = None
_audit_engine = None
_command_registry: CommandRegistry | None = None
_rule_engine: RuleEngine | None = None
_fallback_bus: EventBus | None = None
_fallback_player_secret: str | None = None
_fallback_rng: GameRng | None = None
_fallback_meters: MeterService | None = None
_fallback_effects: EffectService | None = None


@dataclass
class CommandResult:
    """Result of a web command execution."""

    new_feed_messages: list[dict[str, Any]] = field(default_factory=list)
    room_changed: bool = False
    new_room: Room | None = None
    inventory_changed: bool = False
    new_inventory: list[dict[str, Any]] = field(default_factory=list)
    minimap_changed: bool = False
    exits: list[dict] = field(default_factory=list)
    player_id: str = ""
    dialogue: JsonObject | None = None
    dialogue_changed: bool = False
    quest_changed: bool = False


def get_engines(request: Request | None = None):
    """Return (game_engine, audit_engine).

    Prefer the ones attached by the app lifespan (real server + tests).
    Fall back to module-level lazy creation for direct router use.
    """
    if request is not None:
        try:
            st = getattr(getattr(request, "app", None), "state", None)
            lore = getattr(st, "lorecraft", None) if st else None
            if lore is not None:
                ge = getattr(lore, "game_engine", None)
                ae = getattr(lore, "audit_engine", None)
                if ge is not None and ae is not None:
                    return ge, ae
        except (AttributeError, TypeError):
            log.debug("app_state_engine_access_failed")

    global _game_engine, _audit_engine
    if _game_engine is None:
        from lorecraft.config import load_settings
        from lorecraft.db import create_tables

        settings = load_settings()
        _game_engine = create_game_engine(settings)
        _audit_engine = create_audit_engine(settings)
        create_tables(
            game_engine=_game_engine, audit_engine=_audit_engine, settings=settings
        )
    return _game_engine, _audit_engine


def get_app_state(request: Request | None) -> AppState | None:
    """Extract AppState from request, or None if unavailable."""
    if request is None:
        return None
    try:
        state = getattr(request.app.state, "lorecraft", None)
        if isinstance(state, AppState):
            return state
    except (AttributeError, TypeError):
        log.debug("app_state_access_failed")
    return None


def get_command_engine(request: Request | None = None) -> CommandEngine:
    """Get the CommandEngine, preferring app.state; falls back to global."""
    app_state = get_app_state(request)
    if app_state is not None:
        return app_state.command_engine

    global _command_registry, _rule_engine
    if _command_registry is None:
        _command_registry = CommandRegistry()
        _rule_engine = RuleEngine()
        register_item_rules(_rule_engine)
        from lorecraft.commands import register_all_commands

        register_all_commands(_command_registry)
    return CommandEngine(_command_registry, _rule_engine or RuleEngine())


def get_manager() -> ConnectionManager:
    """Get the ConnectionManager. Fallback for when not in app.state."""
    return ConnectionManager()


def get_real_manager(request: Request) -> ConnectionManager | None:
    """Attempt to extract the real ConnectionManager from request.app.state."""
    try:
        state = getattr(request.app.state, "lorecraft", None)
        if state and hasattr(state, "manager"):
            return state.manager
    except (AttributeError, TypeError):
        log.debug("app_state_manager_access_failed")
    return None


def get_bus(request: Request) -> EventBus:
    """Get the EventBus, preferring app.state; falls back to global."""
    try:
        state = getattr(request.app.state, "lorecraft", None)
        if state and hasattr(state, "bus"):
            return state.bus
    except (AttributeError, TypeError):
        log.debug("app_state_bus_access_failed")
    global _fallback_bus
    if _fallback_bus is None:
        _fallback_bus = EventBus()
    return _fallback_bus


def get_rng(request: Request) -> GameRng:
    """Get the app-wide GameRng, preferring app.state; falls back to an
    unseeded (OS-entropy) instance — only reachable when app.state.lorecraft
    isn't wired up (e.g. a router tested in isolation)."""
    try:
        state = getattr(request.app.state, "lorecraft", None)
        if state and hasattr(state, "rng"):
            return state.rng
    except (AttributeError, TypeError):
        log.debug("app_state_rng_access_failed")
    global _fallback_rng
    if _fallback_rng is None:
        _fallback_rng = GameRng()
    return _fallback_rng


def get_meters(request: Request) -> MeterService:
    """Get the app-wide MeterService, preferring app.state; falls back to a
    lazily-constructed instance bound to the fallback engine (router tested
    in isolation)."""
    try:
        state = getattr(request.app.state, "lorecraft", None)
        if state and hasattr(state, "meters"):
            return state.meters
    except (AttributeError, TypeError):
        log.debug("app_state_meters_access_failed")
    global _fallback_meters
    if _fallback_meters is None:
        game_engine, _audit_engine_ = get_engines(request)
        _fallback_meters = MeterService(game_engine, get_rng(request))
    return _fallback_meters


def get_effects(request: Request) -> EffectService:
    """Get the app-wide EffectService, preferring app.state; falls back to a
    lazily-constructed instance bound to the fallback engine (router tested
    in isolation)."""
    try:
        state = getattr(request.app.state, "lorecraft", None)
        if state and hasattr(state, "effects"):
            return state.effects
    except (AttributeError, TypeError):
        log.debug("app_state_effects_access_failed")
    global _fallback_effects
    if _fallback_effects is None:
        game_engine, _audit_engine_ = get_engines(request)
        _fallback_effects = EffectService(game_engine, get_rng(request))
    return _fallback_effects


def player_session_secret(app_state: AppState | None) -> str:
    """Secret used to sign/verify the player session cookie."""
    if app_state is not None and app_state.settings.player_session_secret:
        return app_state.settings.player_session_secret
    global _fallback_player_secret
    if _fallback_player_secret is None:
        _fallback_player_secret = secrets.token_hex(32)
    return _fallback_player_secret


def player_session_ttl(app_state: AppState | None) -> int:
    """TTL for player session cookies in seconds."""
    if app_state is not None:
        return app_state.settings.player_session_ttl_seconds
    return 60 * 60 * 24 * 7


def set_player_session_cookie(
    resp: Any, player_id: str, app_state: AppState | None
) -> None:
    """Set a signed player session cookie on the response."""
    ttl = player_session_ttl(app_state)
    token = create_player_token(player_id, player_session_secret(app_state), ttl)
    resp.set_cookie(
        key=PLAYER_SESSION_COOKIE,
        value=token,
        max_age=ttl,
        httponly=True,
        samesite="lax",
    )


def ensure_player_session(player: Player, db: DBSession) -> str:
    """Ensure there's an active PlayerSession row for the player."""
    from lorecraft.engine.models.session import PlayerSession

    now = time.time()
    ps = PlayerRepo(db).active_session(player.id)
    if ps is None:
        ps = PlayerSession(
            id=f"web-{player.id}-{int(now)}",
            player_id=player.id,
            connected_at=now,
            status="active",
        )
        db.add(ps)
        db.commit()
        db.refresh(ps)
    return ps.id


def inventory_snapshot(player: Player, item_repo: ItemRepo) -> list[dict[str, Any]]:
    """Build a snapshot of the player's inventory for display."""
    items: list[dict[str, Any]] = []
    for stack, item in item_repo.stacks_carried_by(player.id):
        items.append(
            {
                "id": item.id,
                "name": item.name,
                "description_short": (item.description or "")[:60],
                "quantity": stack.quantity,
                "usable": False,
                "droppable": True,
            }
        )
    return items


def encumbrance_snapshot_for(
    session: DBSession, player_repo: PlayerRepo, player_id: str
) -> dict[str, float | str]:
    """Carry-weight summary for the inventory panel (Sprint 49). Reads the
    player's strength for capacity; defaults to 10 if stats are missing."""
    from lorecraft.features.encumbrance.rules import encumbrance_snapshot

    stats = player_repo.stats(player_id)
    strength = stats.strength if stats is not None else 10
    return encumbrance_snapshot(session, player_id, strength)


def room_panel_context(
    room: Room | None,
    room_repo: RoomRepo,
    item_repo: ItemRepo,
    player: Player,
    *,
    npc_repo: NpcRepo,
) -> dict[str, Any]:
    """Build context data for the room panel (exits, items, NPCs)."""
    from lorecraft.features.inventory.service import room_items_visible_labels

    if room is None:
        return {"exits": [], "items_visible": [], "npcs": []}

    return {
        "exits": room_repo.get_exits_with_names(
            room.id,
            visited=player.visited_rooms,
        ),
        "items_visible": room_items_visible_labels(room.id, item_repo.items_in_room),
        "npcs": [npc.name for npc in npc_repo.in_room(room.id)],
    }


def active_quests_snapshot(
    player: Player, quest_repo: QuestRepo
) -> list[dict[str, Any]]:
    """Build a snapshot of the player's active quests."""
    quests: list[dict[str, Any]] = []
    for progress in quest_repo.active_progress(player.id):
        quest = quest_repo.get(progress.quest_id)
        if quest is None:
            continue
        stage = next(
            (s for s in quest.stages if s["id"] == progress.current_stage_id),
            None,
        )
        quests.append(
            {
                "quest_id": progress.quest_id,
                "title": quest.title,
                "stage_description": str(stage.get("description", "")) if stage else "",
                "status": progress.status,
            }
        )
    return quests


def world_time_snapshot(room_repo: RoomRepo) -> dict[str, Any]:
    """Build a snapshot of the current world time."""
    clock = room_repo.world_clock()
    if clock is None:
        return {}
    return {
        "hour": clock.current_hour,
        "minute": clock.current_minute,
        "day": clock.current_day,
        "season": clock.current_season,
        "weather": clock.weather,
    }


def format_idle_duration(seconds: float) -> str:
    """Compact idle label for the Here Now panel."""
    total_minutes = max(0, int(seconds // 60))
    if total_minutes < 1:
        return "Away"
    if total_minutes < 60:
        return f"Idle {total_minutes}m"
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if minutes:
        return f"Idle {hours}h{minutes}m"
    return f"Idle {hours}h"


def presence_for_player(
    player_id: str,
    *,
    manager: ConnectionManager | None,
    player_repo: PlayerRepo,
    now: float | None = None,
) -> dict[str, Any]:
    """Presence state for Here Now: online, grace (reconnecting), or away/idle."""
    current_time = time.time() if now is None else now
    if manager is not None and manager.is_connected(player_id):
        return {
            "is_online": True,
            "presence": "online",
            "status_label": None,
        }

    session = player_repo.latest_session(player_id)
    if session is not None and session.status == "grace":
        return {
            "is_online": False,
            "presence": "grace",
            "status_label": "Reconnecting…",
        }

    idle_seconds = 0.0
    if session is not None and session.disconnected_at is not None:
        idle_seconds = current_time - session.disconnected_at
    label = format_idle_duration(idle_seconds) if idle_seconds >= 60 else "Away"
    return {
        "is_online": False,
        "presence": "away",
        "status_label": label,
    }


def players_here(
    player: Player,
    room_id: str | None,
    manager: ConnectionManager | None,
    player_repo: PlayerRepo,
) -> list[dict[str, Any]]:
    """Build list of players in the room, with presence info."""

    def _entry(other: Player) -> dict[str, Any]:
        pres = presence_for_player(other.id, manager=manager, player_repo=player_repo)
        return {
            "name": other.username,
            "is_self": other.id == player.id,
            **pres,
        }

    if not room_id:
        return [_entry(player)]

    entries = [_entry(other) for other in player_repo.in_room(room_id)]
    if not any(entry["is_self"] for entry in entries):
        entries.insert(0, _entry(player))
    return entries


def expire_grace_periods(
    game_db: DBSession,
    audit_db: DBSession,
    bus: EventBus,
    *,
    grace_seconds: float,
) -> None:
    """Expire any grace periods that have elapsed."""
    SessionSafetyService(
        game_session=game_db,
        audit_session=audit_db,
        bus=bus,
        grace_seconds=grace_seconds,
    ).expire_due_grace_periods()
