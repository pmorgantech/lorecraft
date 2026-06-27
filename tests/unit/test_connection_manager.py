import asyncio

from lorecraft.game.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message) -> None:
        self.messages.append(message)


def test_connection_manager_tracks_room_membership() -> None:
    asyncio.run(_test_connection_manager_tracks_room_membership())


async def _test_connection_manager_tracks_room_membership() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket()

    await manager.connect("player-1", ws, room_id="tavern")

    assert ws.accepted is True
    assert manager.players_in_room("tavern") == ["player-1"]

    manager.move_player("player-1", "tavern", "square")

    assert manager.players_in_room("tavern") == []
    assert manager.players_in_room("square") == ["player-1"]


def test_connection_manager_broadcasts_to_room_with_exclude() -> None:
    asyncio.run(_test_connection_manager_broadcasts_to_room_with_exclude())


async def _test_connection_manager_broadcasts_to_room_with_exclude() -> None:
    manager = ConnectionManager()
    ws_1 = FakeWebSocket()
    ws_2 = FakeWebSocket()

    await manager.connect("player-1", ws_1, room_id="tavern")
    await manager.connect("player-2", ws_2, room_id="tavern")

    await manager.broadcast_to_room(
        "tavern", {"type": "room_message"}, exclude="player-1"
    )

    assert ws_1.messages == []
    assert ws_2.messages == [{"type": "room_message"}]


def test_connection_manager_disconnect_keeps_room_position_for_reconnect_grace() -> (
    None
):
    asyncio.run(
        _test_connection_manager_disconnect_keeps_room_position_for_reconnect_grace()
    )


async def _test_connection_manager_disconnect_keeps_room_position_for_reconnect_grace() -> (
    None
):
    manager = ConnectionManager()
    ws = FakeWebSocket()

    await manager.connect("player-1", ws, room_id="tavern")
    await manager.disconnect("player-1")

    assert manager.players_in_room("tavern") == ["player-1"]
