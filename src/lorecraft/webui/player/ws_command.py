"""Shared WebSocket command-handling core.

The body of what used to be `main._handle_websocket_command`, lifted out so the
live `/ws` handler *and* the Rust-port gateway adapter
(`lorecraft.gateway.adapter`) execute one identical command pipeline — same
disambiguation resolution, frozen-session guard, `build_game_context` →
`CommandEngine.handle_command` → `broadcast_command_effects` sequence, legacy
`command_result` envelope, and crash-capture fallback. The only injected
difference is the connection manager: the `/ws` handler passes the real
`ConnectionManager` (frames go to live sockets); the gateway adapter passes a
`DirectiveConnectionManager` (fan-out is recorded as `DeliveryDirective`s). This
keeps the two transports from drifting — decision 5 of the Phase 3 spec ("reuses
ALL existing command + fan-out logic").

Composition/web-host layer: imports engine + player-UI projection, never
`main`, so the gateway adapter can reuse it without an import cycle once a later
task wires the adapter into the app factory.
"""

from __future__ import annotations

import logging

from sqlmodel import Session

from lorecraft.engine.game.broadcast import broadcast_command_effects
from lorecraft.engine.game.connection_manager import ConnectionManagerProtocol
from lorecraft.engine.game.context import build_game_context
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.crash_reports import record_crash
from lorecraft.observability import bind_transaction_context
from lorecraft.state import AppState
from lorecraft.types import JsonObject, JsonValue
from lorecraft.webui.player.messages import (
    EXECUTION_ERROR_MESSAGE,
    FROZEN_SESSION_MESSAGE,
)
from lorecraft.webui.player.ui_snapshots import player_ui_updates

log = logging.getLogger(__name__)


async def handle_ws_command(
    state: AppState,
    manager: ConnectionManagerProtocol,
    player_id: str,
    session_id: str,
    command: str,
) -> JsonObject:
    """Run one player command and return its legacy `command_result` frame.

    `manager` receives all room/global fan-out for the command (via
    `broadcast_command_effects`); the returned dict is the direct reply for the
    acting player. Both are transport-agnostic — a real `ConnectionManager`
    delivers to sockets, a `DirectiveConnectionManager` records directives.
    """
    # Resolve a bare number as a disambiguation choice.
    stripped = command.strip()
    if stripped.isdigit():
        pending = state.pending_disambig.pop(player_id, None)
        if pending is not None:
            choices: list[str] = pending.get("choices", [])  # type: ignore[assignment]
            idx = int(stripped) - 1
            if 0 <= idx < len(choices):
                verb: str = pending.get("verb", "examine")  # type: ignore[assignment]
                command = f"{verb} {choices[idx]}"
            # If out of range, fall through to normal (unknown) command handling.

    with (
        Session(state.game_engine) as game_session,
        Session(state.audit_engine) as audit_session,
    ):
        player_repo = PlayerRepo(game_session)
        room_repo = RoomRepo(game_session)
        player = player_repo.get(player_id)
        if player is None:
            return {
                "type": "error",
                "message": "Player no longer exists.",
            }
        pre_room_id = player.current_room_id

        # Frozen session check
        active_session = player_repo.player_session(session_id)
        if active_session is not None and active_session.status == "frozen":
            return {
                "type": "system",
                "text": FROZEN_SESSION_MESSAGE,
            }

        room = room_repo.get(player.current_room_id)
        if room is None:
            return {
                "type": "error",
                "message": "Player room no longer exists.",
            }

        transaction = TransactionContext.create(
            actor_id=player.id,
            correlation_id=session_id,
        )
        try:
            ctx = build_game_context(
                game_session,
                player,
                room,
                bus=state.bus,
                manager=manager,
                transaction=transaction,
                session_id=session_id,
                rng=state.rng,
                meters=state.meters,
                effects=state.effects,
                clock=room_repo.world_clock(),
                audit_session=audit_session,
                commit_state=game_session.commit,
                commit_audit=audit_session.commit,
                rollback_state=game_session.rollback,
            )
            with bind_transaction_context(
                transaction.transaction_id, transaction.correlation_id
            ):
                parsed = state.command_engine.handle_command(command, ctx)
            await broadcast_command_effects(manager, ctx, pre_room_id=pre_room_id)
            messages: list[JsonValue] = list(ctx.messages)
            room_messages: list[JsonValue] = list(ctx.room_messages)
            # Chat echoes carry their channel (Sprint 52) so clients can tag/color
            # per channel; older clients reading only `text` degrade gracefully.
            chat_messages: list[JsonValue] = [
                {"text": echo.text, "channel": echo.channel} for echo in ctx.chat_echoes
            ]

            # Capture and store any pending disambiguation; don't send to client.
            disambig = ctx.updates.pop("disambig_pending", None)
            if disambig is not None and isinstance(disambig, dict):
                state.pending_disambig[player_id] = disambig

            updates = {
                **ctx.updates,
                **player_ui_updates(player, ctx.room, room_repo, ctx.item_repo),
            }
            response: JsonObject = {
                "type": "command_result",
                "command": parsed.raw,
                "verb": parsed.verb,
                "noun": parsed.noun,
                "messages": messages,
                "room_messages": room_messages,
                "chat_messages": chat_messages,
                "updates": updates,
            }
            return response
        except Exception as exc:
            # Sprint 57.3: anything that escapes the command pipeline itself
            # (as opposed to a handler exception, already caught and
            # reported gracefully inside CommandEngine) previously killed the
            # WebSocket outright. Capture it and degrade to an in-game error
            # instead of a raw disconnect.
            log.exception("unhandled_command_pipeline_exception")
            game_session.rollback()
            record_crash(
                audit_session,
                transaction_id=transaction.transaction_id,
                correlation_id=transaction.correlation_id,
                player_id=player.id,
                command_text=command,
                exc=exc,
            )
            return {
                "type": "error",
                "message": EXECUTION_ERROR_MESSAGE,
            }
