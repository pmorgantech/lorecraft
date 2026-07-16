"""Admin push WebSocket endpoint."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import jwt
from fastapi import WebSocket, WebSocketDisconnect

from lorecraft.webui.admin.auth import decode_token
from lorecraft.state import AppState
from lorecraft.types import JsonObject

log = logging.getLogger(__name__)


async def admin_ws_endpoint(websocket: WebSocket, app_state: AppState) -> None:
    """Accept admin WS connections; push events, accept subscribe commands."""
    token_str = websocket.query_params.get("token", "")
    # Accept the handshake *before* validating so that, on a bad/expired token,
    # the client receives an application close code (1008) it can act on — the
    # admin UI uses 1008 to distinguish a stale session (force logout) from a
    # transient network drop (reconnect). Closing before accept would reject the
    # handshake at the HTTP layer, and the browser would only see 1006.
    await websocket.accept()
    try:
        decode_token(token_str, app_state.settings.admin_jwt_secret)
    except jwt.InvalidTokenError as e:
        log.error("admin_ws_token_invalid: %s", str(e))
        await websocket.close(code=1008, reason="Invalid or missing token")
        return

    q: asyncio.Queue[JsonObject] = asyncio.Queue(maxsize=200)
    app_state.admin_broadcaster.add(q)
    observed_players: dict[str, Callable[[], None]] = {}

    sender = asyncio.create_task(_send_loop(websocket, q))
    try:
        while True:
            try:
                msg = await websocket.receive_json()
                _handle_subscribe_message(msg, app_state, q, observed_players)
            except WebSocketDisconnect:
                break
            except Exception as e:
                log.debug("admin_ws_receive_error: %s", str(e))
                break
    finally:
        for unsubscribe in observed_players.values():
            unsubscribe()
        sender.cancel()
        app_state.admin_broadcaster.remove(q)
        try:
            await sender
        except asyncio.CancelledError:
            pass


async def _send_loop(ws: WebSocket, q: asyncio.Queue[JsonObject]) -> None:
    while True:
        msg = await q.get()
        try:
            await ws.send_json(msg)
        except Exception as e:
            log.debug("admin_ws_send_error: %s", str(e))
            break


def _handle_subscribe_message(
    msg: object,
    app_state: AppState,
    q: asyncio.Queue[JsonObject],
    observed_players: dict[str, Callable[[], None]],
) -> None:
    if not isinstance(msg, dict):
        return
    msg_type = msg.get("type")
    player_id = str(msg.get("player_id", "")).strip()
    if not player_id:
        return
    if msg_type == "observe_player":
        if player_id in observed_players:
            return

        def mirror(message: JsonObject) -> None:
            try:
                q.put_nowait(
                    {
                        "type": "player_observed_output",
                        "player_id": player_id,
                        "message": message,
                    }
                )
            except asyncio.QueueFull:
                pass

        observed_players[player_id] = app_state.manager.observe_player_output(
            player_id, mirror
        )
    elif msg_type == "unobserve_player":
        unsubscribe = observed_players.pop(player_id, None)
        if unsubscribe is not None:
            unsubscribe()
