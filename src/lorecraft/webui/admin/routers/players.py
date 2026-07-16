"""Admin API router for player management (list, state, teleport, flags, freeze)."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from lorecraft.errors import GameError, NotFoundError
from lorecraft.webui.admin.auth import Moderator, Observer
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.broadcast import broadcast_command_effects
from lorecraft.engine.game.context import build_game_context
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.transaction import TransactionContext, TransactionSource
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.session import PlayerSession
from lorecraft.engine.repos.audit_repo import AuditRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.features.equipment.body import (
    player_body_snapshot,
)
from lorecraft.observability import bind_transaction_context

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


def _require_reason(reason: str | None) -> str:
    value = (reason or "").strip()
    if not value:
        raise HTTPException(status_code=422, detail="Admin reason is required")
    return value


def _player_snapshot(player: Player) -> dict[str, Any]:
    return {
        "id": player.id,
        "username": player.username,
        "current_room_id": player.current_room_id,
        "respawn_room_id": player.respawn_room_id,
        "pvp_consent": player.pvp_consent,
        "ghost_state": player.ghost_state,
        "flags": player.flags,
    }


def _player_body_snapshot(session: Session, player: Player) -> dict[str, Any]:
    return dict(player_body_snapshot(session, player.id))


def _meter_snapshot(meter: Any) -> dict[str, Any]:
    return {
        "key": meter.key,
        "current": meter.current,
        "maximum": meter.maximum,
    }


def _set_meter_full(
    state: Any, session: Session, player_id: str, key: str
) -> dict[str, Any] | None:
    try:
        meter = state.meters.get(session, "player", player_id, key)
    except NotFoundError:
        return None
    before = _meter_snapshot(meter)
    state.meters.set_current(session, meter, meter.maximum)
    return {"key": key, "before": before, "after": _meter_snapshot(meter)}


def _audit_admin_action(
    state: Any,
    *,
    admin_username: str,
    action: str,
    target_id: str,
    reason: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    with Session(state.audit_engine) as audit_session:
        AuditRepo(audit_session).record(
            AuditEvent(
                transaction_id=str(uuid4()),
                correlation_id=f"admin-{action}-{int(time.time() * 1000)}",
                actor_id=admin_username,
                event_type="admin_action",
                source_type=TransactionSource.ADMIN.value,
                target_id=target_id,
                room_id="",
                game_time=0.0,
                real_time=time.time(),
                severity="WARNING",
                summary=(
                    f"Admin '{admin_username}' performed {action} "
                    f"on player '{target_id}'."
                ),
                payload_json={
                    "action": action,
                    "reason": reason,
                    "before": before or {},
                    "after": after or {},
                },
            )
        )
        audit_session.commit()


@router.get("/players")
async def list_players(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    online_ids = set(state.manager._connections.keys())
    with Session(state.game_engine) as session:
        players = session.exec(select(Player)).all()
        session_rows = session.exec(
            select(PlayerSession).order_by(col(PlayerSession.connected_at).desc())
        ).all()
        latest_sessions: dict[str, PlayerSession] = {}
        for row in session_rows:
            latest_sessions.setdefault(row.player_id, row)
        stack_repo = StackRepo(session)
        rows: list[dict[str, Any]] = []
        for p in players:
            latest = latest_sessions.get(p.id)
            activity_state = "combat" if p.active_combat_session_id else "idle"
            if p.ghost_state:
                activity_state = "ghost"
            rows.append(
                {
                    "id": p.id,
                    "username": p.username,
                    "current_room_id": p.current_room_id,
                    "online": p.id in online_ids,
                    "activity_state": activity_state,
                    "session_status": latest.status if latest else "none",
                    "last_seen_at": (
                        latest.disconnected_at or latest.connected_at
                        if latest
                        else None
                    ),
                    "pvp_consent": p.pvp_consent,
                    "ghost_state": p.ghost_state,
                    "active_combat_session_id": p.active_combat_session_id,
                    "inventory_count": sum(
                        stack.quantity
                        for stack in stack_repo.stacks_for_owner("player", p.id)
                    ),
                    "flags": p.flags,
                }
            )
        return rows


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
        body_snapshot = _player_body_snapshot(session, player)
        return {
            "id": player.id,
            "username": player.username,
            "current_room_id": player.current_room_id,
            "respawn_room_id": player.respawn_room_id,
            "inventory": [
                {
                    "item_id": stack.item_id,
                    "quantity": stack.quantity,
                    "instance_id": stack.instance_id,
                }
                for stack in stack_repo.stacks_for_owner("player", player.id)
            ],
            **body_snapshot,
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


@router.get("/players/{player_id}/observe")
async def observe_player(
    player_id: str, request: Request, _: Observer, limit: int = 25
) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        stack_repo = StackRepo(session)
        body_snapshot = _player_body_snapshot(session, player)
        snapshot = {
            **_player_snapshot(player),
            "online": player.id in state.manager._connections,
            "visited_rooms": player.visited_rooms,
            "inventory": [
                {
                    "item_id": stack.item_id,
                    "quantity": stack.quantity,
                    "instance_id": stack.instance_id,
                }
                for stack in stack_repo.stacks_for_owner("player", player.id)
            ],
            **body_snapshot,
        }
    with Session(state.audit_engine) as audit_session:
        events = AuditRepo(audit_session).recent_for_actor(
            player_id, limit=min(limit, 100)
        )
    return {
        "player": snapshot,
        "recent_events": [
            {
                "id": e.id,
                "transaction_id": e.transaction_id,
                "correlation_id": e.correlation_id,
                "event_type": e.event_type,
                "room_id": e.room_id,
                "real_time": e.real_time,
                "severity": e.severity,
                "summary": e.summary,
                "payload": e.payload_json,
            }
            for e in events
        ],
    }


class _TeleportBody(BaseModel):
    room_id: str
    reason: str | None = None


@router.post("/players/{player_id}/teleport")
async def teleport_player(
    player_id: str, body: _TeleportBody, request: Request, admin: Moderator
) -> dict[str, str]:
    reason = _require_reason(body.reason)
    state = _state(request)
    with (
        Session(state.game_engine) as session,
        Session(state.audit_engine) as audit_session,
    ):
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        before = _player_snapshot(player)
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
            rules=state.rules,
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
        after = _player_snapshot(player)

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

    _audit_admin_action(
        state,
        admin_username=admin.username,
        action="player.teleport",
        target_id=player_id,
        reason=reason,
        before=before,
        after=after,
    )
    await state.manager.send_to_player(
        player_id, {"type": "room_change", "room": room_payload}
    )
    return {"status": "teleported", "player_id": player_id, "room_id": target_id}


class _FlagsBody(BaseModel):
    flags: dict[str, Any]
    reason: str | None = None


class _PlayerUpdateBody(BaseModel):
    username: str | None = None
    respawn_room_id: str | None = None
    pvp_consent: bool | None = None
    ghost_state: bool | None = None
    flags: dict[str, Any] | None = None
    reason: str | None = None


@router.patch("/players/{player_id}")
async def update_player(
    player_id: str, body: _PlayerUpdateBody, request: Request, admin: Moderator
) -> dict[str, Any]:
    reason = _require_reason(body.reason)
    state = _state(request)
    with Session(state.game_engine) as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        before = _player_snapshot(player)

        if body.username is not None:
            username = body.username.strip()
            if not username:
                raise HTTPException(status_code=422, detail="Username is required")
            existing = session.exec(
                select(Player).where(Player.username == username)
            ).first()
            if existing is not None and existing.id != player_id:
                raise HTTPException(status_code=409, detail="Username already exists")
            player.username = username

        if body.respawn_room_id is not None:
            respawn_room_id = body.respawn_room_id.strip()
            if not respawn_room_id:
                raise HTTPException(status_code=422, detail="Respawn room is required")
            respawn_room = RoomRepo(session).resolve_ref(respawn_room_id)
            if respawn_room is None:
                raise HTTPException(status_code=404, detail="Respawn room not found")
            player.respawn_room_id = respawn_room.id

        if body.pvp_consent is not None:
            player.pvp_consent = body.pvp_consent
        if body.ghost_state is not None:
            player.ghost_state = body.ghost_state
        if body.flags is not None:
            player.flags = body.flags

        session.add(player)
        session.commit()
        session.refresh(player)
        after = _player_snapshot(player)
    _audit_admin_action(
        state,
        admin_username=admin.username,
        action="player.update",
        target_id=player_id,
        reason=reason,
        before=before,
        after=after,
    )
    return after


@router.post("/players/{player_id}/flags")
async def set_player_flags(
    player_id: str, body: _FlagsBody, request: Request, admin: Moderator
) -> dict[str, Any]:
    reason = _require_reason(body.reason)
    state = _state(request)
    with Session(state.game_engine) as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        before = _player_snapshot(player)
        player.flags = {**player.flags, **body.flags}
        session.add(player)
        session.commit()
        after = _player_snapshot(player)
    _audit_admin_action(
        state,
        admin_username=admin.username,
        action="player.flags",
        target_id=player_id,
        reason=reason,
        before=before,
        after=after,
    )
    return {"player_id": player_id, "flags": after["flags"]}


class _ReasonBody(BaseModel):
    reason: str | None = None


class _HealBody(BaseModel):
    reason: str | None = None
    amount: float | None = Field(default=None, gt=0)


@router.post("/players/{player_id}/heal")
async def heal_player(
    player_id: str, body: _HealBody, request: Request, admin: Moderator
) -> dict[str, Any]:
    reason = _require_reason(body.reason)
    state = _state(request)
    with Session(state.game_engine) as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        meter = state.meters.get(session, "player", player_id, "hp")
        before = _meter_snapshot(meter)
        if body.amount is None:
            state.meters.set_current(session, meter, meter.maximum)
        else:
            state.meters.adjust(session, meter, body.amount)
        after = _meter_snapshot(meter)
        session.commit()

    _audit_admin_action(
        state,
        admin_username=admin.username,
        action="player.heal",
        target_id=player_id,
        reason=reason,
        before={"hp": before},
        after={"hp": after},
    )
    await state.manager.send_to_player(
        player_id,
        {"type": "system", "text": "An administrator restores your health."},
    )
    return {"status": "healed", "player_id": player_id, "meter": after}


@router.post("/players/{player_id}/revitalize")
async def revitalize_player(
    player_id: str, body: _ReasonBody, request: Request, admin: Moderator
) -> dict[str, Any]:
    reason = _require_reason(body.reason)
    state = _state(request)
    meter_changes: list[dict[str, Any]] = []
    with Session(state.game_engine) as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        for key in ("hp", "fatigue"):
            change = _set_meter_full(state, session, player_id, key)
            if change is not None:
                meter_changes.append(change)
        session.commit()

    _audit_admin_action(
        state,
        admin_username=admin.username,
        action="player.revitalize",
        target_id=player_id,
        reason=reason,
        before={"meters": [m["before"] for m in meter_changes]},
        after={"meters": [m["after"] for m in meter_changes]},
    )
    await state.manager.send_to_player(
        player_id,
        {"type": "system", "text": "An administrator revitalizes you."},
    )
    return {"status": "revitalized", "player_id": player_id, "meters": meter_changes}


class _BuffBody(BaseModel):
    effect_key: str
    reason: str | None = None
    duration_ticks: float = Field(default=60.0, gt=0)
    amount: float | None = None


@router.post("/players/{player_id}/buff")
async def buff_player(
    player_id: str, body: _BuffBody, request: Request, admin: Moderator
) -> dict[str, Any]:
    reason = _require_reason(body.reason)
    effect_key = body.effect_key.strip()
    if not effect_key:
        raise HTTPException(status_code=422, detail="effect_key is required")
    state = _state(request)
    with Session(state.game_engine) as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        clock = RoomRepo(session).world_clock()
        payload: dict[str, Any] = {}
        if body.amount is not None:
            payload["amount"] = body.amount
        try:
            effect = state.effects.apply(
                session,
                "player",
                player_id,
                effect_key,
                duration_ticks=body.duration_ticks,
                payload=payload,
                clock_epoch=clock.game_epoch if clock is not None else 0.0,
            )
        except GameError as exc:
            raise HTTPException(status_code=422, detail=exc.message) from exc
        after = {
            "effect_id": effect.id,
            "effect_key": effect.effect_key,
            "payload": effect.payload,
            "expires_at_epoch": effect.expires_at_epoch,
        }
        session.commit()

    _audit_admin_action(
        state,
        admin_username=admin.username,
        action="player.buff",
        target_id=player_id,
        reason=reason,
        after={"effect": after},
    )
    await state.manager.send_to_player(
        player_id,
        {"type": "system", "text": f"An administrator bestows {effect_key} on you."},
    )
    return {"status": "buffed", "player_id": player_id, "effect": after}


class _BestowBody(BaseModel):
    reason: str | None = None
    coins: int = Field(default=0, ge=0)
    item_id: str | None = None
    quantity: int = Field(default=1, ge=1)


@router.post("/players/{player_id}/bestow")
async def bestow_player(
    player_id: str, body: _BestowBody, request: Request, admin: Moderator
) -> dict[str, Any]:
    reason = _require_reason(body.reason)
    item_id = body.item_id.strip() if body.item_id is not None else None
    if body.coins <= 0 and not item_id:
        raise HTTPException(status_code=422, detail="Bestow coins or an item")
    state = _state(request)
    with Session(state.game_engine) as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        before_balance = LedgerService().balance_of(session, "player", player_id)
        if body.coins:
            LedgerService().credit(session, "player", player_id, body.coins)
        stacks: list[dict[str, Any]] = []
        if item_id:
            try:
                created = ItemLocationService(session).spawn(
                    item_id,
                    Location("player", player_id),
                    quantity=body.quantity,
                )
            except GameError as exc:
                raise HTTPException(status_code=422, detail=exc.message) from exc
            stacks = [
                {
                    "stack_id": stack.id,
                    "item_id": stack.item_id,
                    "quantity": stack.quantity,
                    "instance_id": stack.instance_id,
                }
                for stack in created
            ]
        after_balance = LedgerService().balance_of(session, "player", player_id)
        session.commit()

    before = {"coins": before_balance}
    after = {
        "coins": after_balance,
        "coins_granted": body.coins,
        "items": stacks,
    }
    _audit_admin_action(
        state,
        admin_username=admin.username,
        action="player.bestow",
        target_id=player_id,
        reason=reason,
        before=before,
        after=after,
    )
    awarded: list[str] = []
    if body.coins:
        awarded.append(f"{body.coins} coins")
    if item_id:
        awarded.append(f"{body.quantity} {item_id}")
    await state.manager.send_to_player(
        player_id,
        {"type": "system", "text": f"An administrator gives you {', '.join(awarded)}."},
    )
    return {"status": "bestowed", "player_id": player_id, **after}


@router.post("/players/{player_id}/freeze")
async def freeze_player(
    player_id: str, body: _ReasonBody, request: Request, admin: Moderator
) -> dict[str, str]:
    reason = _require_reason(body.reason)
    state = _state(request)
    with Session(state.game_engine) as session:
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
    _audit_admin_action(
        state,
        admin_username=admin.username,
        action="player.freeze",
        target_id=player_id,
        reason=reason,
    )
    await state.manager.send_to_player(
        player_id,
        {"type": "system", "text": "Your session has been frozen by an administrator."},
    )
    return {"status": "frozen", "player_id": player_id}


@router.post("/players/{player_id}/unfreeze")
async def unfreeze_player(
    player_id: str, body: _ReasonBody, request: Request, admin: Moderator
) -> dict[str, str]:
    reason = _require_reason(body.reason)
    state = _state(request)
    with Session(state.game_engine) as session:
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
    _audit_admin_action(
        state,
        admin_username=admin.username,
        action="player.unfreeze",
        target_id=player_id,
        reason=reason,
    )
    await state.manager.send_to_player(
        player_id,
        {"type": "system", "text": "Your session has been unfrozen."},
    )
    return {"status": "unfrozen", "player_id": player_id}
