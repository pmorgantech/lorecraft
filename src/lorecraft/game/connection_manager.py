"""WebSocket connection pool and room-based broadcasts."""

from __future__ import annotations

from collections import defaultdict

from lorecraft.types import JsonObject, JsonWebSocket


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

    async def send_to_player(self, player_id: str, message: JsonObject) -> None:
        ws = self._connections.get(player_id)
        if ws is None:
            return
        await ws.send_json(message)

    async def broadcast_to_room(
        self,
        room_id: str,
        message: JsonObject,
        exclude: str | None = None,
    ) -> None:
        for player_id in self.players_in_room(room_id):
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
