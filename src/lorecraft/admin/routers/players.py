"""Admin API router for player management (list, state, teleport, flags, freeze)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, col, select

from lorecraft.admin.auth import Moderator, Observer
from lorecraft.models.player import Player
from lorecraft.models.world import Room

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


@router.get("/players")
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


@router.get("/players/{player_id}/state")
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


@router.post("/players/{player_id}/teleport")
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


@router.post("/players/{player_id}/flags")
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


@router.post("/players/{player_id}/freeze")
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


@router.post("/players/{player_id}/unfreeze")
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
