"""VirtualPlayer — a real WebSocket client for the simulation harness.

Wraps a `websockets` connection to the game's `/ws` endpoint the same way a
real client would, so scripted scenarios exercise the actual wire protocol
(JSON frames over a real socket) instead of an ASGI-transport shortcut.
`websockets` ships as a transitive dependency of `fastapi[standard]` and is
declared explicitly in `pyproject.toml`'s `dev` extra since this module
imports it directly.
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

JsonObject = dict[str, Any]

_DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass
class VirtualPlayer:
    player_id: str
    username: str
    _ws: ClientConnection
    messages: list[JsonObject] = field(default_factory=list)

    @classmethod
    async def connect(
        cls,
        ws_url: str,
        player_id: str,
        username: str,
        *,
        ticket: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> VirtualPlayer:
        """Open the socket and consume the initial `connected` handshake message.

        Two auth transports, selected by whether a `ticket` is supplied:

        - `ticket=None` (default): the legacy `?player_id=` query path, used by
          the Python-direct simulation server (which enables
          `allow_query_player_id`). Exercises the raw wire protocol without the
          login UI.
        - `ticket=<single-use ws-ticket>`: the real `?ticket=` path required by
          the Rust gateway front door, which does **not** accept `?player_id=`.
          Mint the ticket via `POST /auth/ws-ticket` (see
          `SimulationServer.prepare_login`).
        """
        query = f"ticket={ticket}" if ticket is not None else f"player_id={player_id}"
        ws = await websockets.connect(f"{ws_url}/ws?{query}")
        player = cls(player_id=player_id, username=username, _ws=ws)
        handshake = await asyncio.wait_for(player._recv(), timeout=timeout)
        if handshake.get("type") != "connected":
            raise RuntimeError(f"unexpected handshake message: {handshake!r}")
        return player

    async def _recv(self) -> JsonObject:
        raw = await self._ws.recv()
        message: JsonObject = json.loads(raw)
        self.messages.append(message)
        return message

    async def send_command(
        self, command: str, *, timeout: float = _DEFAULT_TIMEOUT_SECONDS
    ) -> JsonObject:
        """Send one command and return its direct `command_result` reply.

        Broadcasts pushed from other players' actions (`player_joined`,
        `player_left`, ...) can arrive interleaved on this same socket; they
        are recorded in `self.messages` but skipped here, since the reply to
        *this* command is always the next `command_result` frame.
        """
        await self._ws.send(command)
        return await asyncio.wait_for(self._await_command_result(), timeout=timeout)

    async def _await_command_result(self) -> JsonObject:
        while True:
            message = await self._recv()
            if message.get("type") == "command_result":
                return message

    async def wait_for_broadcast(
        self, message_type: str, *, timeout: float = _DEFAULT_TIMEOUT_SECONDS
    ) -> JsonObject:
        """Block until a pushed (non-reply) message of the given type arrives."""

        async def _wait() -> JsonObject:
            while True:
                message = await self._recv()
                if message.get("type") == message_type:
                    return message

        return await asyncio.wait_for(_wait(), timeout=timeout)

    async def run_script(
        self, script: list[str], *, timing_jitter_ms: int = 0
    ) -> list[JsonObject]:
        """Send each command in order, with an optional random delay first."""
        results: list[JsonObject] = []
        for command in script:
            if timing_jitter_ms:
                await asyncio.sleep(random.uniform(0, timing_jitter_ms) / 1000)
            results.append(await self.send_command(command))
        return results

    def broadcasts(self) -> list[JsonObject]:
        """Messages pushed to this connection that weren't a direct reply."""
        return [m for m in self.messages if m.get("type") != "command_result"]

    async def close(self) -> None:
        await self._ws.close()
