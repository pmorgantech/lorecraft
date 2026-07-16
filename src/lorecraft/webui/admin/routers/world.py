"""Admin API router for world editing: rooms, items, NPCs, and changesets."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from lorecraft.webui.admin.auth import Observer, Superadmin, WorldBuilder
from lorecraft.models.changeset import ConflictScanResult
from lorecraft.engine.models.world import Item, NPC, Room
from lorecraft.engine.repos.meter_repo import MeterRepo
from lorecraft.world.bootstrap import resolve_world_yaml_path
from lorecraft.world.reseed import reseed_world_from_yaml
from lorecraft.world.validator import WorldValidationError
from lorecraft.world.versioning import VersioningService

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


# ---------------------------------------------------------------------------
# Destructive ops: full DB wipe + reseed from world.yaml (Sprint 72.2)
# ---------------------------------------------------------------------------


class _ReseedResponse(BaseModel):
    status: str
    rooms: int
    items: int
    room_items: int
    npcs: int
    quests: int
    relocated_players: int


@router.post("/world/reseed")
async def reseed_world(request: Request, _: Superadmin) -> _ReseedResponse:
    """Wipe all authored world content and reseed it from `world.yaml`.

    Destructive and superadmin-gated. The YAML is validated *before* anything is
    deleted, so a malformed `world.yaml` returns 422 and leaves the DB untouched
    rather than half-applying. Players stranded in a now-deleted room are moved
    to the configured seed start room (see `reseed_world_from_yaml`).
    """
    state = _state(request)
    world_path = resolve_world_yaml_path(state.settings.world_yaml_path)
    if not world_path.is_file():
        raise HTTPException(
            status_code=404, detail=f"World YAML not found: {world_path}"
        )
    try:
        result = reseed_world_from_yaml(
            state.game_engine, world_path, settings=state.settings
        )
    except WorldValidationError as exc:
        raise HTTPException(
            status_code=422, detail=f"world.yaml is invalid: {exc}"
        ) from exc
    return _ReseedResponse(
        status="reseeded",
        rooms=result.rooms,
        items=result.items,
        room_items=result.room_items,
        npcs=result.npcs,
        quests=result.quests,
        relocated_players=result.relocated_players,
    )


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
            "map_z": r.map_z,
            "zone": r.zone,
            "room_type": r.room_type,
            "indoor": r.indoor,
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
    map_z: int | None = None
    zone: str | None = None
    room_type: str | None = None
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
        if body.map_z is not None:
            room.map_z = body.map_z
        if body.zone is not None:
            room.zone = body.zone
        if body.room_type is not None:
            room.room_type = body.room_type
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
    map_z: int = 0
    zone: str | None = None
    room_type: str | None = None
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
            map_z=body.map_z,
            zone=body.zone,
            room_type=body.room_type,
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
    return [_item_response(i) for i in items]


class _CreateItemBody(BaseModel):
    id: str
    name: str
    description: str
    takeable: bool = True
    tradeable: bool = True
    bound: bool = False
    aliases: list[str] = Field(default_factory=list)
    usable_with: list[str] = Field(default_factory=list)
    loot_table: dict[str, Any] = Field(default_factory=dict)
    slot: str | None = None
    wearable: bool = False
    weight: float = Field(default=0.0, ge=0.0)
    quality: str = "common"
    max_durability: int | None = Field(default=None, ge=0)
    light: int = Field(default=0, ge=0)
    capacity: float | None = Field(default=None, ge=0.0)
    effects: list[dict[str, Any]] = Field(default_factory=list)
    value: int = Field(default=0, ge=0)
    category: str | None = None
    mechanism_states: list[str] = Field(default_factory=list)
    mechanism_side_effects: dict[str, Any] = Field(default_factory=dict)
    combination_side_effects: dict[str, Any] = Field(default_factory=dict)
    context_commands: dict[str, Any] = Field(default_factory=dict)


class _UpdateItemBody(BaseModel):
    name: str | None = None
    description: str | None = None
    takeable: bool | None = None
    tradeable: bool | None = None
    bound: bool | None = None
    aliases: list[str] | None = None
    usable_with: list[str] | None = None
    loot_table: dict[str, Any] | None = None
    slot: str | None = None
    wearable: bool | None = None
    weight: float | None = Field(default=None, ge=0.0)
    quality: str | None = None
    max_durability: int | None = Field(default=None, ge=0)
    light: int | None = Field(default=None, ge=0)
    capacity: float | None = Field(default=None, ge=0.0)
    effects: list[dict[str, Any]] | None = None
    value: int | None = Field(default=None, ge=0)
    category: str | None = None
    mechanism_states: list[str] | None = None
    mechanism_side_effects: dict[str, Any] | None = None
    combination_side_effects: dict[str, Any] | None = None
    context_commands: dict[str, Any] | None = None


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail=f"{field_name} is required")
    return cleaned


def _item_response(item: Item) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "takeable": item.takeable,
        "tradeable": item.tradeable,
        "bound": item.bound,
        "aliases": item.aliases,
        "usable_with": item.usable_with,
        "loot_table": item.loot_table,
        "slot": item.slot,
        "wearable": item.wearable,
        "weight": item.weight,
        "quality": item.quality,
        "max_durability": item.max_durability,
        "light": item.light,
        "capacity": item.capacity,
        "effects": item.effects,
        "value": item.value,
        "category": item.category,
        "mechanism_states": item.mechanism_states,
        "mechanism_side_effects": item.mechanism_side_effects,
        "combination_side_effects": item.combination_side_effects,
        "context_commands": item.context_commands,
    }


@router.post("/world/items")
async def create_item(
    body: _CreateItemBody, request: Request, _: WorldBuilder
) -> dict[str, Any]:
    item_id = _clean_required_text(body.id, "Item id")
    state = _state(request)
    with Session(state.game_engine) as session:
        if session.get(Item, item_id) is not None:
            raise HTTPException(
                status_code=409, detail=f"Item {item_id!r} already exists"
            )
        item = Item(
            id=item_id,
            name=_clean_required_text(body.name, "Item name"),
            description=_clean_required_text(body.description, "Item description"),
            takeable=body.takeable,
            tradeable=body.tradeable,
            bound=body.bound,
            aliases=body.aliases,
            usable_with=body.usable_with,
            loot_table=body.loot_table,
            slot=_clean_optional_text(body.slot),
            wearable=body.wearable,
            weight=body.weight,
            quality=_clean_required_text(body.quality, "Item quality"),
            max_durability=body.max_durability,
            light=body.light,
            capacity=body.capacity,
            effects=body.effects,
            value=body.value,
            category=_clean_optional_text(body.category),
            mechanism_states=body.mechanism_states,
            mechanism_side_effects=body.mechanism_side_effects,
            combination_side_effects=body.combination_side_effects,
            context_commands=body.context_commands,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return {"status": "created", **_item_response(item)}


@router.put("/world/items/{item_id}")
async def update_item(
    item_id: str, body: _UpdateItemBody, request: Request, _: WorldBuilder
) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        item = session.get(Item, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")

        fields_set = body.model_fields_set
        if "name" in fields_set:
            item.name = _clean_required_text(body.name or "", "Item name")
        if "description" in fields_set:
            item.description = _clean_required_text(
                body.description or "", "Item description"
            )
        if body.takeable is not None:
            item.takeable = body.takeable
        if body.tradeable is not None:
            item.tradeable = body.tradeable
        if body.bound is not None:
            item.bound = body.bound
        if body.aliases is not None:
            item.aliases = body.aliases
        if body.usable_with is not None:
            item.usable_with = body.usable_with
        if body.loot_table is not None:
            item.loot_table = body.loot_table
        if "slot" in fields_set:
            item.slot = _clean_optional_text(body.slot)
        if body.wearable is not None:
            item.wearable = body.wearable
        if body.weight is not None:
            item.weight = body.weight
        if body.quality is not None:
            item.quality = _clean_required_text(body.quality, "Item quality")
        if "max_durability" in fields_set:
            item.max_durability = body.max_durability
        if body.light is not None:
            item.light = body.light
        if "capacity" in fields_set:
            item.capacity = body.capacity
        if body.effects is not None:
            item.effects = body.effects
        if body.value is not None:
            item.value = body.value
        if "category" in fields_set:
            item.category = _clean_optional_text(body.category)
        if body.mechanism_states is not None:
            item.mechanism_states = body.mechanism_states
        if body.mechanism_side_effects is not None:
            item.mechanism_side_effects = body.mechanism_side_effects
        if body.combination_side_effects is not None:
            item.combination_side_effects = body.combination_side_effects
        if body.context_commands is not None:
            item.context_commands = body.context_commands

        session.add(item)
        session.commit()
        session.refresh(item)
        return {"status": "updated", **_item_response(item)}


# ---------------------------------------------------------------------------
# NPCs
# ---------------------------------------------------------------------------


@router.get("/world/npcs")
async def list_npcs(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        npcs = session.exec(select(NPC)).all()
        meter_repo = MeterRepo(session)
        rooms = {room.id: room for room in session.exec(select(Room)).all()}
        rows: list[dict[str, Any]] = []
        for npc in npcs:
            room = rooms.get(npc.current_room_id)
            rows.append(
                {
                    "id": npc.id,
                    "name": npc.name,
                    "description": npc.description,
                    "current_room_id": npc.current_room_id,
                    "current_room_name": room.name if room else None,
                    "home_room_id": npc.home_room_id,
                    "dialogue_tree_id": npc.dialogue_tree_id,
                    "behavior": npc.behavior,
                    "current_hp": _npc_current_hp(meter_repo, npc),
                    "max_hp": npc.max_hp,
                    "respawn_seconds": npc.respawn_seconds,
                    "schedule_count": len(npc.schedule),
                    "schedule": npc.schedule,
                    "ai": npc.ai,
                    "following_player_id": npc.following_player_id,
                    "context_command_count": len(npc.context_commands),
                    "context_commands": sorted(npc.context_commands.keys()),
                    "trigger_count": len(npc.triggers),
                    "loot_table": npc.loot_table,
                }
            )
        return rows


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
