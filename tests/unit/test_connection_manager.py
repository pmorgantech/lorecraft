"""Unit tests for ConnectionManager."""

from __future__ import annotations

from lorecraft.engine.game.connection_manager import ConnectionManager


def test_is_connected_reflects_registration() -> None:
    manager = ConnectionManager()
    assert manager.is_connected("player-1") is False
    manager.move_player("player-1", None, "tavern")
    assert manager.is_connected("player-1") is False
    manager._connections["player-1"] = object()  # type: ignore[assignment]
    assert manager.is_connected("player-1") is True
