"""Admin push WebSocket endpoint."""

from __future__ import annotations

import asyncio
import logging

import jwt
from fastapi import WebSocket, WebSocketDisconnect

from lorecraft.webui.admin.auth import decode_token
from lorecraft.state import AppState
from lorecraft.types import JsonObject

log = logging.getLogger(__name__)


async def admin_ws_endpoint(websocket: WebSocket, app_state: AppState) -> None:
    """Accept admin WS connections; push events, accept subscribe commands."""
    token_str = websocket.query_params.get("token", "")
    try:
        decode_token(token_str, app_state.settings.admin_jwt_secret)
    except jwt.InvalidTokenError as e:
        log.error("admin_ws_token_invalid: %s", str(e))
        await websocket.close(code=1008, reason="Invalid or missing token")
        return

    await websocket.accept()
    q: asyncio.Queue[JsonObject] = asyncio.Queue(maxsize=200)
    app_state.admin_broadcaster.add(q)

    sender = asyncio.create_task(_send_loop(websocket, q))
    try:
        while True:
            try:
                await websocket.receive_json()  # subscribe commands — no-op for now
            except WebSocketDisconnect:
                break
            except Exception as e:
                log.debug("admin_ws_receive_error: %s", str(e))
                break
    finally:
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
