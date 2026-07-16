"""Unit tests for ConnectionManager."""

from __future__ import annotations

import asyncio

from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.types import JsonObject


class _FakeSocket:
    """JsonWebSocket stand-in; optionally raises on send like a dying socket."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[JsonObject] = []

    async def accept(self) -> None:  # pragma: no cover - protocol completeness
        pass

    async def send_json(self, data: JsonObject) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append(data)


def test_is_connected_reflects_registration() -> None:
    manager = ConnectionManager()
    assert manager.is_connected("player-1") is False
    manager.move_player("player-1", None, "tavern")
    assert manager.is_connected("player-1") is False
    manager._connections["player-1"] = object()  # type: ignore[assignment]
    assert manager.is_connected("player-1") is True


def test_send_failure_drops_the_connection_instead_of_raising() -> None:
    """Any send failure means the socket is dead/dying (the concrete type is
    host-framework-specific — e.g. starlette's WebSocketDisconnect during a
    broadcast racing a close). It must be absorbed and the connection dropped,
    never propagated to the broadcasting caller."""

    class _Disconnected(Exception):
        pass

    manager = ConnectionManager()
    manager._connections["player-1"] = _FakeSocket(error=_Disconnected())  # type: ignore[assignment]
    manager.move_player("player-1", None, "tavern")

    asyncio.run(manager.send_to_player("player-1", {"type": "player_left"}))

    assert manager.is_connected("player-1") is False
    assert manager.players_in_room("tavern") == []


def test_broadcast_survives_one_dead_socket() -> None:
    manager = ConnectionManager()
    dead = _FakeSocket(error=RuntimeError("connection is closing"))
    alive = _FakeSocket()
    manager._connections["dead"] = dead  # type: ignore[assignment]
    manager._connections["alive"] = alive  # type: ignore[assignment]
    manager.move_player("dead", None, "tavern")
    manager.move_player("alive", None, "tavern")

    asyncio.run(manager.broadcast_to_room("tavern", {"type": "feed_append"}))

    assert [m["type"] for m in alive.sent] == ["feed_append"]
    assert manager.is_connected("dead") is False
    assert manager.is_connected("alive") is True


def test_send_to_player_mirrors_messages_to_output_observers() -> None:
    manager = ConnectionManager()
    observed: list[JsonObject] = []

    unsubscribe = manager.observe_player_output("player-1", observed.append)

    asyncio.run(manager.send_to_player("player-1", {"type": "feed_append"}))
    unsubscribe()
    asyncio.run(manager.send_to_player("player-1", {"type": "ignored"}))

    assert [m["type"] for m in observed] == ["feed_append"]


def test_broken_output_observer_does_not_block_send() -> None:
    manager = ConnectionManager()
    observed: list[JsonObject] = []

    def broken(_message: JsonObject) -> None:
        raise RuntimeError("observer gone")

    manager.observe_player_output("player-1", broken)
    manager.observe_player_output("player-1", observed.append)

    asyncio.run(manager.send_to_player("player-1", {"type": "feed_append"}))
    asyncio.run(manager.send_to_player("player-1", {"type": "state_change"}))

    assert [m["type"] for m in observed] == ["feed_append", "state_change"]
