"""Admin API router for player management (list, state, teleport, flags, freeze)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, col, select

from lorecraft.webui.admin.auth import Moderator, Observer
from lorecraft.engine.game.broadcast import broadcast_command_effects
from lorecraft.engine.game.context import build_game_context
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.observability import bind_transaction_context

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


@router.get("/players")
async def list_players(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    online_ids = set(state.manager._connections.keys())
    with Session(state.game_engine) as session:
        players = session.exec(select(Player)).all()
        stack_repo = StackRepo(session)
        return [
            {
                "id": p.id,
                "username": p.username,
                "current_room_id": p.current_room_id,
                "online": p.id in online_ids,
                "inventory_count": sum(
                    stack.quantity
                    for stack in stack_repo.stacks_for_owner("player", p.id)
                ),
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
        from lorecraft.engine.models.session import PlayerSession

        player_sessions = list(
            session.exec(
                select(PlayerSession)
                .where(PlayerSession.player_id == player_id)
                .order_by(col(PlayerSession.connected_at).desc())
                .limit(10)
            ).all()
        )
        stack_repo = StackRepo(session)
        return {
            "id": player.id,
            "username": player.username,
            "current_room_id": player.current_room_id,
            "inventory": [
                {
                    "item_id": stack.item_id,
                    "quantity": stack.quantity,
                    "instance_id": stack.instance_id,
                }
                for stack in stack_repo.stacks_for_owner("player", player.id)
            ],
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
    with (
        Session(state.game_engine) as session,
        Session(state.audit_engine) as audit_session,
    ):
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        # Accept an exact room id, a room name, or a zone-qualified `zone.room`
        # (e.g. `town.inner_vault`) — see RoomRepo.resolve_ref.
        target = RoomRepo(session).resolve_ref(body.room_id)
        if target is None:
            raise HTTPException(
                status_code=404, detail="Target room not found (or name is ambiguous)"
            )
        target_id = target.id

        old_room = player.current_room_id
        player.current_room_id = target_id
        if target_id not in player.visited_rooms:
            player.visited_rooms = player.visited_rooms + [target_id]

        # Route the teleport through the same PLAYER_MOVED machinery a normal walk
        # uses, so room enter/exit behaviour actually fires — encounter triggers,
        # quest/mark progression, follow, and the admin dashboard's live location —
        # instead of silently swapping the field and leaving every client out of sync.
        session_id = f"admin-teleport-{int(time.time() * 1000)}"
        transaction = TransactionContext.create(
            actor_id=player.id, correlation_id=session_id
        )
        ctx = build_game_context(
            session,
            player,
            target,
            bus=state.bus,
            manager=state.manager,
            transaction=transaction,
            session_id=session_id,
            rng=state.rng,
            meters=state.meters,
            effects=state.effects,
            clock=RoomRepo(session).world_clock(),
            audit_session=audit_session,
            commit_state=session.commit,
            commit_audit=audit_session.commit,
            rollback_state=session.rollback,
        )
        state.manager.move_player(player_id, old_room, target_id)
        with bind_transaction_context(
            transaction.transaction_id, transaction.correlation_id
        ):
            ctx.emit(
                GameEvent.PLAYER_MOVED,
                player_id=player_id,
                from_room_id=old_room,
                to_room_id=target_id,
                direction="",
            )
        session.commit()
        audit_session.commit()

        # The actor's own client renders the new room from this payload; other
        # occupants and the admin dashboard resync via broadcast_command_effects.
        room_payload: dict[str, Any] = {
            "id": target.id,
            "name": target.name,
            "description": target.description,
            "map_x": target.map_x,
            "map_y": target.map_y,
            "map_z": target.map_z,
            "exits": [],
        }
        await broadcast_command_effects(state.manager, ctx, pre_room_id=old_room)

    await state.manager.send_to_player(
        player_id, {"type": "room_change", "room": room_payload}
    )
    return {"status": "teleported", "player_id": player_id, "room_id": target_id}


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
        from lorecraft.engine.models.session import PlayerSession

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
        from lorecraft.engine.models.session import PlayerSession

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
