"""Admin API router for world editing: rooms, items, NPCs, and changesets."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from lorecraft.webui.admin.auth import Observer, WorldBuilder
from lorecraft.models.changeset import ConflictScanResult
from lorecraft.engine.models.world import Item, NPC, Room
from lorecraft.engine.repos.meter_repo import MeterRepo
from lorecraft.world.versioning import VersioningService

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------


@router.get("/world/rooms")
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


@router.put("/world/rooms/{room_id}")
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


@router.post("/world/rooms")
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


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


@router.get("/world/items")
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


# ---------------------------------------------------------------------------
# NPCs
# ---------------------------------------------------------------------------


@router.get("/world/npcs")
async def list_npcs(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        npcs = session.exec(select(NPC)).all()
        meter_repo = MeterRepo(session)
        return [
            {
                "id": n.id,
                "name": n.name,
                "current_room_id": n.current_room_id,
                "behavior": n.behavior,
                "current_hp": _npc_current_hp(meter_repo, n),
                "max_hp": n.max_hp,
            }
            for n in npcs
        ]


def _npc_current_hp(meter_repo: MeterRepo, npc: NPC) -> int:
    """Read-only hp lookup — doesn't trigger lazy Meter creation (a GET
    shouldn't have that write side effect); an as-yet-uncreated meter is
    full, matching the "hp" MeterDef's start_full=True."""
    meter = meter_repo.find("npc", npc.id, "hp")
    return int(meter.current) if meter is not None else npc.max_hp


class _SpawnBody(BaseModel):
    room_id: str


@router.post("/npcs/{npc_id}/spawn")
async def spawn_npc(
    npc_id: str, body: _SpawnBody, request: Request, _: WorldBuilder
) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
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


@router.post("/npcs/{npc_id}/despawn")
async def despawn_npc(npc_id: str, request: Request, _: WorldBuilder) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        npc = session.get(NPC, npc_id)
        if npc is None:
            raise HTTPException(status_code=404, detail="NPC not found")
        npc.current_room_id = npc.home_room_id
        session.add(npc)
        session.commit()
    return {"npc_id": npc_id, "status": "despawned", "room_id": npc.home_room_id}


# ---------------------------------------------------------------------------
# Changesets
# ---------------------------------------------------------------------------


@router.get("/changesets")
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


@router.post("/changesets")
async def create_changeset(
    body: _CreateChangesetBody, request: Request, token: WorldBuilder
) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        svc = VersioningService(session)
        cs = svc.create_changeset(name=body.name, created_by=token.username)
        session.commit()
        return {"id": cs.id, "status": cs.status}


@router.get("/changesets/{changeset_id}")
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


@router.post("/changesets/{changeset_id}/scan")
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


@router.post("/changesets/{changeset_id}/promote")
async def promote_changeset(
    changeset_id: str, request: Request, _: WorldBuilder
) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        try:
            VersioningService(session).promote(
                changeset_id, bus=state.bus, manager=state.manager
            )
            session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    return {"changeset_id": changeset_id, "status": "live"}
