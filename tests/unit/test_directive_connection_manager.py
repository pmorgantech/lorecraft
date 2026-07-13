"""DirectiveConnectionManager records a DeliveryDirective per fan-out call and
answers selection queries from its lifecycle-fed read-mirror (Phase 3a)."""

from __future__ import annotations

import asyncio

from lorecraft.gateway.connection_manager import DirectiveConnectionManager
from lorecraft.protocol.gateway import (
    GlobalTarget,
    MovePlayer,
    PlayerTarget,
    RoomTarget,
)


def _drain(mgr: DirectiveConnectionManager) -> list[object]:
    return list(mgr.deliveries)


def test_send_to_player_records_player_directive() -> None:
    mgr = DirectiveConnectionManager()
    asyncio.run(mgr.send_to_player("p1", {"type": "feed_append", "content": "hi"}))

    (directive,) = _drain(mgr)
    assert isinstance(directive.target, PlayerTarget)
    assert directive.target.id == "p1"
    assert directive.exclude is None
    assert directive.payload == {"type": "feed_append", "content": "hi"}


def test_broadcast_to_room_records_room_directive_with_exclude() -> None:
    mgr = DirectiveConnectionManager()
    asyncio.run(
        mgr.broadcast_to_room("tavern", {"type": "player_joined"}, exclude="actor")
    )

    (directive,) = _drain(mgr)
    assert isinstance(directive.target, RoomTarget)
    assert directive.target.id == "tavern"
    assert directive.exclude == "actor"
    assert directive.payload == {"type": "player_joined"}


def test_broadcast_global_records_global_directive() -> None:
    mgr = DirectiveConnectionManager()
    asyncio.run(mgr.broadcast_global({"type": "announce"}, exclude="p9"))

    (directive,) = _drain(mgr)
    assert isinstance(directive.target, GlobalTarget)
    assert directive.exclude == "p9"
    assert directive.payload == {"type": "announce"}


def test_drain_returns_and_clears_the_buffer() -> None:
    mgr = DirectiveConnectionManager()
    asyncio.run(mgr.send_to_player("p1", {"a": 1}))
    asyncio.run(mgr.send_to_player("p2", {"b": 2}))

    first = mgr.drain()
    assert len(first) == 2
    assert mgr.deliveries == []
    assert mgr.drain() == []


def test_move_player_and_room_selection_mirror_the_real_manager() -> None:
    mgr = DirectiveConnectionManager()
    mgr.mark_connected("p1", "tavern")
    mgr.mark_connected("p2", "tavern")
    mgr.mark_connected("p3", "road")

    assert mgr.players_in_room("tavern") == ["p1", "p2"]
    assert mgr.occupied_rooms() == ["road", "tavern"]
    assert mgr.connected_player_ids() == ["p1", "p2", "p3"]

    mgr.move_player("p1", "tavern", "road")
    assert mgr.players_in_room("tavern") == ["p2"]
    assert mgr.players_in_room("road") == ["p1", "p3"]


def test_move_player_records_a_move_frame_for_rust() -> None:
    # A mid-command move both updates the mirror AND records a `MovePlayer` frame so
    # the adapter can forward it to Rust's authoritative registry (gap-1 fix).
    mgr = DirectiveConnectionManager()
    mgr.mark_connected("p1", "tavern")

    mgr.move_player("p1", "tavern", "road")

    (move,) = mgr.drain_moves()
    assert isinstance(move, MovePlayer)
    assert move == MovePlayer(player_id="p1", from_room="tavern", to_room="road")
    # The mirror moved too.
    assert mgr.players_in_room("road") == ["p1"]
    # drain_moves clears the buffer.
    assert mgr.drain_moves() == []


def test_mark_connected_does_not_record_a_move_frame() -> None:
    # Rust learns the connect room from `ConnectAck` (it registers the player
    # there), so a lifecycle connect must update only the mirror — emitting a
    # `MovePlayer` frame here would be a redundant/duplicate registry mutation.
    mgr = DirectiveConnectionManager()
    mgr.mark_connected("p1", "tavern")

    assert mgr.drain_moves() == []
    assert mgr.players_in_room("tavern") == ["p1"]


def test_mark_disconnected_removes_from_mirror_and_session() -> None:
    mgr = DirectiveConnectionManager()
    mgr.mark_connected("p1", "tavern", session_id="s1")
    assert mgr.is_connected("p1") is True
    assert mgr.session_of("p1") == "s1"

    mgr.mark_disconnected("p1")
    assert mgr.is_connected("p1") is False
    assert mgr.session_of("p1") is None
    assert mgr.players_in_room("tavern") == []
    assert mgr.connected_player_ids() == []


def test_directive_manager_satisfies_the_protocol() -> None:
    # Structural check: the concrete manager is usable everywhere the engine
    # seams accept a ConnectionManagerProtocol (no isinstance — protocol is not
    # runtime_checkable; this documents the intent and fails typecheck if broken).
    from lorecraft.engine.game.connection_manager import ConnectionManagerProtocol

    mgr: ConnectionManagerProtocol = DirectiveConnectionManager()
    assert mgr.connected_player_ids() == []
