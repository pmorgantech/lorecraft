"""WebSocket connection pool and room-based broadcasts."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Protocol

from lorecraft.observability import time_operation
from lorecraft.types import JsonObject, JsonWebSocket

log = logging.getLogger(__name__)


class ConnectionManagerProtocol(Protocol):
    """The delivery/selection surface every command + fan-out path depends on.

    ``broadcast_command_effects`` and the command handlers reach the connection
    map only through this fixed set of methods — never socket internals. Typing
    the seams (``GameContext.manager``, ``build_game_context``,
    ``broadcast_command_effects``, ``WorldContext.manager``) against this
    Protocol instead of the concrete :class:`ConnectionManager` makes the manager
    *injectable*: the Rust-port gateway (Phase 3) supplies a
    ``DirectiveConnectionManager`` that records ``DeliveryDirective``s instead of
    awaiting real sockets, and satisfies this surface structurally with no
    changes here. This is a pure Tier 1 generalization (mechanism) — it adds no
    gateway-specific policy to the engine.

    The surface is the seven fan-out/selection methods plus ``is_connected``
    (used by ``commands/social.py`` and ``features/follow/service.py`` via
    ``ctx.manager``), so retyping the seams stays free of ``type: ignore``.
    """

    async def send_to_player(self, player_id: str, message: JsonObject) -> None: ...

    async def broadcast_to_room(
        self, room_id: str, message: JsonObject, exclude: str | None = None
    ) -> None: ...

    async def broadcast_global(
        self, message: JsonObject, exclude: str | None = None
    ) -> None: ...

    def move_player(
        self, player_id: str, from_room: str | None, to_room: str
    ) -> None: ...

    def players_in_room(self, room_id: str) -> list[str]: ...

    def occupied_rooms(self) -> list[str]: ...

    def connected_player_ids(self) -> list[str]: ...

    def is_connected(self, player_id: str) -> bool: ...


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, JsonWebSocket] = {}
        self._player_rooms: dict[str, str] = {}
        self._room_players: dict[str, set[str]] = defaultdict(set)

    async def connect(
        self, player_id: str, ws: JsonWebSocket, room_id: str | None = None
    ) -> None:
        await ws.accept()
        self._connections[player_id] = ws
        if room_id is not None:
            self.move_player(player_id, self._player_rooms.get(player_id), room_id)

    def is_connected(self, player_id: str) -> bool:
        return player_id in self._connections

    async def disconnect(self, player_id: str) -> None:
        self._connections.pop(player_id, None)
        room_id = self._player_rooms.pop(player_id, None)
        if room_id is not None:
            self._room_players[room_id].discard(player_id)

    async def send_to_player(self, player_id: str, message: JsonObject) -> None:
        ws = self._connections.get(player_id)
        if ws is None:
            return
        try:
            await ws.send_json(message)
        except Exception:
            # Transport boundary: a failed send means the socket is dead or
            # dying (the concrete exception type is host-framework-specific —
            # starlette raises WebSocketDisconnect, not just RuntimeError, when
            # a broadcast races a closing connection). Whatever the type, the
            # remedy is the same: drop the connection so one dead socket never
            # breaks a broadcast to everyone else. Never silent — logged with
            # the traceback.
            log.info(
                "dropping connection for %s: send failed", player_id, exc_info=True
            )
            await self.disconnect(player_id)

    async def broadcast_to_room(
        self,
        room_id: str,
        message: JsonObject,
        exclude: str | None = None,
    ) -> None:
        with time_operation("broadcast_send"):
            for player_id in self.players_in_room(room_id):
                if player_id == exclude:
                    continue
                await self.send_to_player(player_id, message)

    async def broadcast_global(
        self,
        message: JsonObject,
        exclude: str | None = None,
    ) -> None:
        """Broadcast a message to all connected players (ignoring rooms)."""
        with time_operation("broadcast_send"):
            for player_id in list(self._connections.keys()):
                if player_id == exclude:
                    continue
                await self.send_to_player(player_id, message)

    def move_player(self, player_id: str, from_room: str | None, to_room: str) -> None:
        if from_room:
            self._room_players[from_room].discard(player_id)
        current_room = self._player_rooms.get(player_id)
        if current_room and current_room != from_room:
            self._room_players[current_room].discard(player_id)
        self._player_rooms[player_id] = to_room
        self._room_players[to_room].add(player_id)

    def players_in_room(self, room_id: str) -> list[str]:
        return sorted(self._room_players.get(room_id, set()))

    def occupied_rooms(self) -> list[str]:
        """Rooms with at least one connected player — lets a world-level broadcast
        (e.g. weather narration) touch only rooms that actually have an audience."""
        return sorted(room for room, players in self._room_players.items() if players)

    def connected_player_ids(self) -> list[str]:
        """Every currently-connected player — the P2ALL chat recipient set
        (Sprint 52.3), letting the broadcast step filter per-recipient
        (channel subscriptions) instead of using the all-or-nothing
        `broadcast_global`."""
        return sorted(self._connections.keys())
