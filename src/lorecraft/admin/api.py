"""Admin REST API router."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, col, select

from lorecraft.admin.auth import (
    Moderator,
    Observer,
    Superadmin,
    WorldBuilder,
    auth_router,
    hash_password,
)
from lorecraft.models.admin import AdminUser
from lorecraft.models.audit import AuditEvent
from lorecraft.models.changeset import ConflictScanResult
from lorecraft.models.player import Player
from lorecraft.models.world import Item, NPC, Room
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.world.versioning import VersioningService

admin_router = APIRouter(tags=["admin"])
admin_router.include_router(auth_router)


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------


@admin_router.get("/players")
async def list_players(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    online_ids = set(state.manager._connections.keys())
    with Session(state.game_engine) as session:
        players = session.exec(select(Player)).all()
        return [
            {
                "id": p.id,
                "username": p.username,
                "current_room_id": p.current_room_id,
                "online": p.id in online_ids,
                "inventory_count": len(p.inventory),
                "flags": p.flags,
            }
            for p in players
        ]


@admin_router.get("/players/{player_id}/state")
async def player_state(player_id: str, request: Request, _: Observer) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        from lorecraft.models.session import PlayerSession

        player_sessions = list(
            session.exec(
                select(PlayerSession)
                .where(PlayerSession.player_id == player_id)
                .order_by(col(PlayerSession.connected_at).desc())
                .limit(10)
            ).all()
        )
        return {
            "id": player.id,
            "username": player.username,
            "current_room_id": player.current_room_id,
            "inventory": player.inventory,
            "visited_rooms": player.visited_rooms,
            "flags": player.flags,
            "pvp_consent": player.pvp_consent,
            "ghost_state": player.ghost_state,
            "online": player.id in state.manager._connections,
            "sessions": [
                {
                    "id": s.id,
                    "status": s.status,
                    "connected_at": s.connected_at,
                    "disconnected_at": s.disconnected_at,
                    "grace_expires_at": s.grace_expires_at,
                }
                for s in player_sessions
            ],
        }


class _TeleportBody(BaseModel):
    room_id: str


@admin_router.post("/players/{player_id}/teleport")
async def teleport_player(
    player_id: str, body: _TeleportBody, request: Request, _: Moderator
) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        target = session.get(Room, body.room_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target room not found")
        old_room = player.current_room_id
        player.current_room_id = body.room_id
        if body.room_id not in player.visited_rooms:
            player.visited_rooms = player.visited_rooms + [body.room_id]
        session.add(player)
        session.commit()
        # Capture before session closes
        room_payload: dict[str, Any] = {
            "id": target.id,
            "name": target.name,
            "description": target.description,
            "map_x": target.map_x,
            "map_y": target.map_y,
            "exits": [],
        }
    state.manager.move_player(player_id, old_room, body.room_id)
    await state.manager.send_to_player(
        player_id, {"type": "room_change", "room": room_payload}
    )
    return {"status": "teleported", "player_id": player_id, "room_id": body.room_id}


class _FlagsBody(BaseModel):
    flags: dict[str, Any]


@admin_router.post("/players/{player_id}/flags")
async def set_player_flags(
    player_id: str, body: _FlagsBody, request: Request, _: Moderator
) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        player.flags = {**player.flags, **body.flags}
        session.add(player)
        session.commit()
        return {"player_id": player_id, "flags": player.flags}


@admin_router.post("/players/{player_id}/freeze")
async def freeze_player(
    player_id: str, request: Request, _: Moderator
) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        from lorecraft.models.session import PlayerSession

        sessions = list(
            session.exec(
                select(PlayerSession).where(
                    PlayerSession.player_id == player_id,
                    PlayerSession.status == "active",
                )
            ).all()
        )
        if not sessions:
            raise HTTPException(status_code=404, detail="No active session for player")
        for s in sessions:
            s.status = "frozen"
            session.add(s)
        session.commit()
    await state.manager.send_to_player(
        player_id,
        {"type": "system", "text": "Your session has been frozen by an administrator."},
    )
    return {"status": "frozen", "player_id": player_id}


@admin_router.post("/players/{player_id}/unfreeze")
async def unfreeze_player(
    player_id: str, request: Request, _: Moderator
) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        from lorecraft.models.session import PlayerSession

        sessions = list(
            session.exec(
                select(PlayerSession).where(
                    PlayerSession.player_id == player_id,
                    PlayerSession.status == "frozen",
                )
            ).all()
        )
        for s in sessions:
            s.status = "active"
            session.add(s)
        session.commit()
    await state.manager.send_to_player(
        player_id,
        {"type": "system", "text": "Your session has been unfrozen."},
    )
    return {"status": "unfrozen", "player_id": player_id}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


@admin_router.get("/audit")
async def query_audit(
    request: Request,
    _: Observer,
    actor: str | None = None,
    room: str | None = None,
    event_type: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.audit_engine) as session:
        stmt = select(AuditEvent).order_by(col(AuditEvent.real_time).desc())
        if actor:
            stmt = stmt.where(AuditEvent.actor_id == actor)
        if room:
            stmt = stmt.where(AuditEvent.room_id == room)
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
        if from_ts is not None:
            stmt = stmt.where(col(AuditEvent.real_time) >= from_ts)
        if to_ts is not None:
            stmt = stmt.where(col(AuditEvent.real_time) <= to_ts)
        stmt = stmt.limit(min(limit, 1000))
        events = session.exec(stmt).all()
    return [
        {
            "id": e.id,
            "transaction_id": e.transaction_id,
            "correlation_id": e.correlation_id,
            "actor_id": e.actor_id,
            "event_type": e.event_type,
            "source_type": e.source_type,
            "target_id": e.target_id,
            "room_id": e.room_id,
            "game_time": e.game_time,
            "real_time": e.real_time,
            "severity": e.severity,
            "summary": e.summary,
            "payload": e.payload_json,
        }
        for e in events
    ]


@admin_router.get("/audit/session/{correlation_id}")
async def session_replay(
    correlation_id: str, request: Request, _: Observer
) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.audit_engine) as session:
        events = session.exec(
            select(AuditEvent)
            .where(AuditEvent.correlation_id == correlation_id)
            .order_by(col(AuditEvent.real_time))
        ).all()
    return [
        {
            "id": e.id,
            "transaction_id": e.transaction_id,
            "actor_id": e.actor_id,
            "event_type": e.event_type,
            "source_type": e.source_type,
            "target_id": e.target_id,
            "room_id": e.room_id,
            "game_time": e.game_time,
            "real_time": e.real_time,
            "severity": e.severity,
            "summary": e.summary,
            "payload": e.payload_json,
        }
        for e in events
    ]


# ---------------------------------------------------------------------------
# World editor — rooms
# ---------------------------------------------------------------------------


@admin_router.get("/world/rooms")
async def list_rooms(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        rooms = session.exec(select(Room)).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "map_x": r.map_x,
            "map_y": r.map_y,
            "area_id": r.area_id,
            "is_active": r.is_active,
            "fallback_room_id": r.fallback_room_id,
            "light_level": r.light_level,
            "disabled_commands": r.disabled_commands,
            "flags": r.flags,
            "version": r.version,
        }
        for r in rooms
    ]


class _RoomBody(BaseModel):
    name: str | None = None
    description: str | None = None
    map_x: int | None = None
    map_y: int | None = None
    area_id: str | None = None
    is_active: bool | None = None
    fallback_room_id: str | None = None
    light_level: int | None = None
    disabled_commands: list[str] | None = None
    flags: dict[str, Any] | None = None
    version: int | None = None  # required for PUT (optimistic lock)


@admin_router.put("/world/rooms/{room_id}")
async def update_room(
    room_id: str, body: _RoomBody, request: Request, _: WorldBuilder
) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        room = session.get(Room, room_id)
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        if body.version is not None and room.version != body.version:
            raise HTTPException(
                status_code=409,
                detail=f"Version conflict: expected {body.version}, found {room.version}",
            )
        if body.name is not None:
            room.name = body.name
        if body.description is not None:
            room.description = body.description
        if body.map_x is not None:
            room.map_x = body.map_x
        if body.map_y is not None:
            room.map_y = body.map_y
        if body.area_id is not None:
            room.area_id = body.area_id
        if body.is_active is not None:
            room.is_active = body.is_active
        if body.fallback_room_id is not None:
            room.fallback_room_id = body.fallback_room_id
        if body.light_level is not None:
            room.light_level = body.light_level
        if body.disabled_commands is not None:
            room.disabled_commands = body.disabled_commands
        if body.flags is not None:
            room.flags = body.flags
        room.version += 1
        session.add(room)
        session.commit()
        session.refresh(room)
        return {"id": room.id, "version": room.version, "status": "updated"}


class _CreateRoomBody(BaseModel):
    id: str
    name: str
    description: str
    map_x: int
    map_y: int
    area_id: str | None = None
    light_level: int = 1


@admin_router.post("/world/rooms")
async def create_room(
    body: _CreateRoomBody, request: Request, _: WorldBuilder
) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        existing = session.get(Room, body.id)
        if existing is not None:
            raise HTTPException(
                status_code=409, detail=f"Room {body.id!r} already exists"
            )
        room = Room(
            id=body.id,
            name=body.name,
            description=body.description,
            map_x=body.map_x,
            map_y=body.map_y,
            area_id=body.area_id,
            light_level=body.light_level,
        )
        session.add(room)
        session.commit()
    return {"id": body.id, "status": "created"}


@admin_router.get("/world/items")
async def list_items(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        items = session.exec(select(Item)).all()
    return [
        {
            "id": i.id,
            "name": i.name,
            "description": i.description,
            "takeable": i.takeable,
            "tradeable": i.tradeable,
        }
        for i in items
    ]


@admin_router.get("/world/npcs")
async def list_npcs(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        npcs = session.exec(select(NPC)).all()
    return [
        {
            "id": n.id,
            "name": n.name,
            "current_room_id": n.current_room_id,
            "behavior": n.behavior,
            "current_hp": n.current_hp,
            "max_hp": n.max_hp,
        }
        for n in npcs
    ]


# ---------------------------------------------------------------------------
# Changesets
# ---------------------------------------------------------------------------


@admin_router.get("/changesets")
async def list_changesets(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        cs_list = VersioningService(session).list_changesets()
    return [
        {
            "id": cs.id,
            "name": cs.name,
            "status": cs.status,
            "created_by": cs.created_by,
            "created_at": cs.created_at,
            "promoted_at": cs.promoted_at,
            "world_version": cs.world_version,
        }
        for cs in cs_list
    ]


class _CreateChangesetBody(BaseModel):
    name: str


@admin_router.post("/changesets")
async def create_changeset(
    body: _CreateChangesetBody, request: Request, token: WorldBuilder
) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        svc = VersioningService(session)
        cs = svc.create_changeset(name=body.name, created_by=token.username)
        session.commit()
        return {"id": cs.id, "status": cs.status}


@admin_router.get("/changesets/{changeset_id}")
async def get_changeset(
    changeset_id: str, request: Request, _: Observer
) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        svc = VersioningService(session)
        cs = svc.get_changeset(changeset_id)
        if cs is None:
            raise HTTPException(status_code=404, detail="Changeset not found")
        items = svc.list_items(changeset_id)
        conflicts = session.exec(
            select(ConflictScanResult).where(
                ConflictScanResult.changeset_id == changeset_id
            )
        ).all()
    return {
        "id": cs.id,
        "name": cs.name,
        "status": cs.status,
        "created_by": cs.created_by,
        "created_at": cs.created_at,
        "promoted_at": cs.promoted_at,
        "world_version": cs.world_version,
        "items": [
            {
                "id": it.id,
                "entity_type": it.entity_type,
                "entity_id": it.entity_id,
                "operation": it.operation,
                "before_state": it.before_state,
                "after_state": it.after_state,
            }
            for it in items
        ],
        "conflicts": [
            {
                "id": c.id,
                "entity_type": c.entity_type,
                "entity_id": c.entity_id,
                "severity": c.severity,
                "auto_resolvable": c.auto_resolvable,
                "acknowledged": c.acknowledged,
                "description": c.description,
            }
            for c in conflicts
        ],
    }


@admin_router.post("/changesets/{changeset_id}/scan")
async def scan_changeset(
    changeset_id: str, request: Request, _: WorldBuilder
) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        svc = VersioningService(session)
        results = svc.scan_conflicts(changeset_id)
        cs = svc.get_changeset(changeset_id)
        session.commit()
    state.admin_broadcaster.push(
        {
            "type": "changeset_scan_done",
            "changeset_id": changeset_id,
            "status": cs.status if cs else "unknown",
            "conflicts": [
                {
                    "severity": r.severity,
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "description": r.description,
                }
                for r in results
            ],
        }
    )
    return {
        "changeset_id": changeset_id,
        "status": cs.status if cs else "unknown",
        "conflict_count": len(results),
        "error_count": sum(1 for r in results if r.severity == "ERROR"),
    }


@admin_router.post("/changesets/{changeset_id}/promote")
async def promote_changeset(
    changeset_id: str, request: Request, _: WorldBuilder
) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        try:
            VersioningService(session).promote(changeset_id, bus=state.bus)
            session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    return {"changeset_id": changeset_id, "status": "live"}


# ---------------------------------------------------------------------------
# Clock control
# ---------------------------------------------------------------------------


@admin_router.get("/clock")
async def get_clock(request: Request, _: Observer) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        clock = RoomRepo(session).world_clock()
    if clock is None:
        raise HTTPException(status_code=503, detail="World clock not initialized")
    return {
        "game_epoch": clock.game_epoch,
        "real_epoch": clock.real_epoch,
        "time_ratio": clock.time_ratio,
        "paused": clock.paused,
        "current_hour": clock.current_hour,
        "current_minute": clock.current_minute,
        "current_day": clock.current_day,
        "current_season": clock.current_season,
        "weather": clock.weather,
    }


@admin_router.post("/clock/pause")
async def pause_clock(request: Request, _: Superadmin) -> dict[str, bool]:
    state = _state(request)
    with Session(state.game_engine) as session:
        clock = RoomRepo(session).world_clock()
        if clock is None:
            raise HTTPException(status_code=503, detail="World clock not initialized")
        clock.paused = True
        session.add(clock)
        session.commit()
    return {"paused": True}


@admin_router.post("/clock/resume")
async def resume_clock(request: Request, _: Superadmin) -> dict[str, bool]:
    state = _state(request)
    with Session(state.game_engine) as session:
        clock = RoomRepo(session).world_clock()
        if clock is None:
            raise HTTPException(status_code=503, detail="World clock not initialized")
        clock.paused = False
        clock.real_epoch = time.time()
        session.add(clock)
        session.commit()
    return {"paused": False}


class _TimeRatioBody(BaseModel):
    ratio: float


@admin_router.post("/clock/time-ratio")
async def set_time_ratio(
    body: _TimeRatioBody, request: Request, _: Superadmin
) -> dict[str, float]:
    if body.ratio <= 0:
        raise HTTPException(status_code=422, detail="ratio must be positive")
    state = _state(request)
    with Session(state.game_engine) as session:
        clock = RoomRepo(session).world_clock()
        if clock is None:
            raise HTTPException(status_code=503, detail="World clock not initialized")
        clock.time_ratio = body.ratio
        session.add(clock)
        session.commit()
    state.clock_runner.time_ratio = body.ratio
    return {"time_ratio": body.ratio}


class _WeatherBody(BaseModel):
    weather: str


_VALID_WEATHER = {
    "clear",
    "light_rain",
    "overcast",
    "hot",
    "thunderstorm",
    "heavy_rain",
    "fog",
    "snow",
    "blizzard",
}


@admin_router.post("/clock/weather")
async def set_weather(
    body: _WeatherBody, request: Request, _: Superadmin
) -> dict[str, str]:
    if body.weather not in _VALID_WEATHER:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown weather. Valid: {sorted(_VALID_WEATHER)}",
        )
    state = _state(request)
    with Session(state.game_engine) as session:
        clock = RoomRepo(session).world_clock()
        if clock is None:
            raise HTTPException(status_code=503, detail="World clock not initialized")
        clock.weather = body.weather
        session.add(clock)
        session.commit()
    return {"weather": body.weather}


# ---------------------------------------------------------------------------
# NPCs
# ---------------------------------------------------------------------------


class _SpawnBody(BaseModel):
    room_id: str


@admin_router.post("/npcs/{npc_id}/spawn")
async def spawn_npc(
    npc_id: str, body: _SpawnBody, request: Request, _: WorldBuilder
) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        from lorecraft.models.world import NPC

        npc = session.get(NPC, npc_id)
        if npc is None:
            raise HTTPException(status_code=404, detail="NPC not found")
        room = session.get(Room, body.room_id)
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        npc.current_room_id = body.room_id
        session.add(npc)
        session.commit()
    return {"npc_id": npc_id, "room_id": body.room_id, "status": "spawned"}


@admin_router.post("/npcs/{npc_id}/despawn")
async def despawn_npc(npc_id: str, request: Request, _: WorldBuilder) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        from lorecraft.models.world import NPC

        npc = session.get(NPC, npc_id)
        if npc is None:
            raise HTTPException(status_code=404, detail="NPC not found")
        npc.current_room_id = npc.home_room_id
        session.add(npc)
        session.commit()
    return {"npc_id": npc_id, "status": "despawned", "room_id": npc.home_room_id}


# ---------------------------------------------------------------------------
# Admin accounts
# ---------------------------------------------------------------------------


class _CreateAdminBody(BaseModel):
    username: str
    password: str
    role: str = "observer"


@admin_router.get("/accounts")
async def list_admin_accounts(request: Request, _: Superadmin) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        users = session.exec(select(AdminUser)).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "created_at": u.created_at,
            "revoked_at": u.revoked_at,
            "active": u.revoked_at is None,
        }
        for u in users
    ]


@admin_router.post("/accounts")
async def create_admin_account(
    body: _CreateAdminBody, request: Request, _: Superadmin
) -> dict[str, str]:
    if body.role not in ("observer", "moderator", "world-builder", "superadmin"):
        raise HTTPException(status_code=422, detail=f"Unknown role: {body.role}")
    state = _state(request)
    with Session(state.game_engine) as session:
        existing = session.exec(
            select(AdminUser).where(AdminUser.username == body.username)
        ).first()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Username already exists")
        user = AdminUser(
            id=str(uuid.uuid4()),
            username=body.username,
            password_hash=hash_password(body.password),
            role=body.role,
            created_at=time.time(),
        )
        session.add(user)
        session.commit()
    return {
        "id": user.id,
        "username": body.username,
        "role": body.role,
        "status": "created",
    }


@admin_router.delete("/accounts/{username}")
async def revoke_admin_account(
    username: str, request: Request, token: Superadmin
) -> dict[str, str]:
    if username == token.username:
        raise HTTPException(status_code=422, detail="Cannot revoke your own account")
    state = _state(request)
    with Session(state.game_engine) as session:
        user = session.exec(
            select(AdminUser).where(AdminUser.username == username)
        ).first()
        if user is None:
            raise HTTPException(status_code=404, detail="Admin user not found")
        user.revoked_at = time.time()
        session.add(user)
        session.commit()
    return {"username": username, "status": "revoked"}
