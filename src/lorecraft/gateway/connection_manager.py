"""Directive-recording connection manager for the Rust-port gateway.

Implements :class:`~lorecraft.engine.game.connection_manager.ConnectionManagerProtocol`
so it can be injected wherever the real `ConnectionManager` goes — into
`build_game_context`, `broadcast_command_effects`, and the command handlers —
but instead of awaiting live WebSockets, every send/broadcast is *recorded* as a
:class:`~lorecraft.protocol.gateway.DeliveryDirective`. The gateway adapter drains
those directives after each command (or lifecycle event) and forwards them to the
Rust gateway, which owns the authoritative connection map and resolves recipients.

Selection methods (`players_in_room`, `connected_player_ids`, `occupied_rooms`,
`is_connected`, `move_player`) answer from a lightweight **read-mirror** of the
connection map — the same three-map shape the real manager keeps — fed by the
gateway lifecycle events (`mark_connected`/`mark_disconnected`) and by mid-command
`move_player` calls. Per Phase 3 decision 5 the mirror is *advisory for selection
only*: Rust's map is the delivery source of truth, so a directive addressed to a
player who has since disconnected is a harmless downstream no-op — exactly the
real manager's "socket is None -> return" behavior.
"""

from __future__ import annotations

from collections import defaultdict

from lorecraft.protocol.gateway import (
    DeliveryDirective,
    GlobalTarget,
    PlayerTarget,
    RoomTarget,
)
from lorecraft.types import JsonObject


class DirectiveConnectionManager:
    """A `ConnectionManagerProtocol` that records `DeliveryDirective`s."""

    def __init__(self) -> None:
        self.deliveries: list[DeliveryDirective] = []
        # Read-mirror of the connection map (advisory, Rust is authoritative).
        self._connected: set[str] = set()
        self._player_rooms: dict[str, str] = {}
        self._room_players: dict[str, set[str]] = defaultdict(set)
        # player_id -> session_id, remembered from mark_connected so the adapter's
        # disconnect teardown can begin the grace period without the session id on
        # the wire (the `Disconnected` frame carries only player_id + reason).
        self._sessions: dict[str, str] = {}

    # -- ConnectionManagerProtocol: delivery (records directives) -----------

    async def send_to_player(self, player_id: str, message: JsonObject) -> None:
        self.deliveries.append(
            DeliveryDirective(
                target=PlayerTarget(id=player_id), exclude=None, payload=message
            )
        )

    async def broadcast_to_room(
        self, room_id: str, message: JsonObject, exclude: str | None = None
    ) -> None:
        self.deliveries.append(
            DeliveryDirective(
                target=RoomTarget(id=room_id), exclude=exclude, payload=message
            )
        )

    async def broadcast_global(
        self, message: JsonObject, exclude: str | None = None
    ) -> None:
        self.deliveries.append(
            DeliveryDirective(target=GlobalTarget(), exclude=exclude, payload=message)
        )

    # -- ConnectionManagerProtocol: selection (reads the mirror) ------------

    def move_player(self, player_id: str, from_room: str | None, to_room: str) -> None:
        """Mirror the real manager's mid-command room move (synchronous)."""
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
        return sorted(room for room, players in self._room_players.items() if players)

    def connected_player_ids(self) -> list[str]:
        return sorted(self._connected)

    def is_connected(self, player_id: str) -> bool:
        return player_id in self._connected

    # -- lifecycle-fed mirror maintenance (not part of the protocol) --------

    def mark_connected(
        self, player_id: str, room_id: str, session_id: str | None = None
    ) -> None:
        """Register a newly-connected player in the mirror (adapter `Connected`)."""
        self._connected.add(player_id)
        if session_id is not None:
            self._sessions[player_id] = session_id
        self.move_player(player_id, self._player_rooms.get(player_id), room_id)

    def mark_disconnected(self, player_id: str) -> None:
        """Drop a player from the mirror (adapter `Disconnected`)."""
        self._connected.discard(player_id)
        self._sessions.pop(player_id, None)
        room_id = self._player_rooms.pop(player_id, None)
        if room_id is not None:
            self._room_players[room_id].discard(player_id)

    def session_of(self, player_id: str) -> str | None:
        """The session id last recorded for `player_id` at connect time, if any."""
        return self._sessions.get(player_id)

    # -- adapter buffer draining --------------------------------------------

    def drain(self) -> list[DeliveryDirective]:
        """Return and clear the directives recorded since the last drain."""
        recorded = self.deliveries
        self.deliveries = []
        return recorded
