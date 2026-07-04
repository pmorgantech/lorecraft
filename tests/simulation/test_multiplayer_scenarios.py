"""Multi-player scripted scenarios over real WebSockets (Sprints 12 & 14).

These complement the single-connection ASGI-transport integration tests
(`tests/integration/test_admin_websocket.py` et al.) with scenarios that only
show up once *multiple real* players are connected concurrently: room
broadcast fan-out on connect and on command execution, and contention over a
single shared item.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from tests.simulation.conftest import SimulationServer
from tests.simulation.virtual_player import VirtualPlayer

pytestmark = pytest.mark.simulation


def _username(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _connect(server: SimulationServer, prefix: str) -> VirtualPlayer:
    username = _username(prefix)
    player_id = server.create_player(username)
    return await VirtualPlayer.connect(server.ws_url, player_id, username)


def test_player_joined_broadcast_reaches_other_player_in_room(
    simulation_server: SimulationServer,
) -> None:
    asyncio.run(_test_player_joined_broadcast(simulation_server))


async def _test_player_joined_broadcast(server: SimulationServer) -> None:
    """Both new characters start in the same room (village_square); a second
    real connection should push a `player_joined` broadcast to the first."""
    bob = await _connect(server, "bob")
    try:
        alice_username = _username("alice")
        alice_id = server.create_player(alice_username)
        alice = await asyncio.wait_for(
            VirtualPlayer.connect(server.ws_url, alice_id, alice_username),
            timeout=5,
        )
        try:
            joined = await bob.wait_for_broadcast("player_joined", timeout=5)
            assert joined["username"] == alice_username
            assert joined["player_id"] == alice_id
        finally:
            await alice.close()
    finally:
        await bob.close()


def test_command_room_messages_broadcast_to_other_ws_players(
    simulation_server: SimulationServer,
) -> None:
    """Sprint 14 closed a gap Sprint 12 surfaced: the raw `/ws` command loop
    now re-broadcasts a command's `ctx.room_messages` (and a `state_change`
    nudge) to other WS-connected room occupants, the same way `POST /command`
    already did — one shared `broadcast_command_effects()` step for both.
    Bug fix (2026-07-04): movement also broadcasts an arrival narration
    (`ctx.arrival_messages`) to the destination room, not just a departure
    narration to the room left — previously arrivals were completely silent
    (only a panel-refresh nudge, no feed message)."""
    asyncio.run(_test_command_room_broadcast(simulation_server))


async def _test_command_room_broadcast(server: SimulationServer) -> None:
    alice = await _connect(server, "alice")
    bob = await _connect(server, "bob")
    try:
        # Moving rooms: the departure narration ("X leaves east.") broadcasts
        # to the room left (where bob still is), and — since Sprint 15.2 — a
        # state_change nudge also reaches bob there so his players-online
        # panel refreshes once alice is gone.
        await alice.send_command("go east")

        feed = await bob.wait_for_broadcast("feed_append", timeout=5)
        assert feed["message_type"] == "room_event"
        assert "leaves" in str(feed["content"]).lower()

        state_change_left = await bob.wait_for_broadcast("state_change", timeout=5)
        assert state_change_left["actor_id"] == alice.player_id
        assert "players-online" in state_change_left["affected_panels"]

        # Moving back into bob's room: an arrival narration ("X arrives from
        # the east.") now reaches him, followed by the state_change nudge
        # (always sent to the destination room).
        await alice.send_command("go west")
        feed_arrival = await bob.wait_for_broadcast("feed_append", timeout=5)
        assert feed_arrival["message_type"] == "room_event"
        assert "arrives" in str(feed_arrival["content"]).lower()

        state_change = await bob.wait_for_broadcast("state_change", timeout=5)
        assert state_change["actor_id"] == alice.player_id
        assert "room-description" in state_change["affected_panels"]
    finally:
        await alice.close()
        await bob.close()


def test_concurrent_take_of_a_single_item_has_no_duplication(
    simulation_server: SimulationServer,
) -> None:
    asyncio.run(_test_concurrent_take(simulation_server))


async def _test_concurrent_take(server: SimulationServer) -> None:
    """village_square has exactly one copper_coin. Two players racing to take
    it must not both succeed, and the coin must not be duplicated or lost."""
    alice = await _connect(server, "alice")
    bob = await _connect(server, "bob")
    try:
        results = await asyncio.gather(
            alice.run_script(["take coin"], timing_jitter_ms=20),
            bob.run_script(["take coin"], timing_jitter_ms=20),
        )
        alice_result, bob_result = results[0][0], results[1][0]

        alice_inventory = server.player_inventory(alice.player_id)
        bob_inventory = server.player_inventory(bob.player_id)
        coin_holders = [
            inv for inv in (alice_inventory, bob_inventory) if _has_coin(inv)
        ]
        assert len(coin_holders) == 1, (
            f"expected exactly one winner, got alice={alice_inventory} "
            f"bob={bob_inventory}"
        )

        winner_messages, loser_messages = (
            (alice_result["messages"], bob_result["messages"])
            if _has_coin(alice_inventory)
            else (bob_result["messages"], alice_result["messages"])
        )
        assert any("take" in str(m).lower() for m in winner_messages)
        assert any("don't see" in str(m).lower() for m in loser_messages)
    finally:
        await alice.close()
        await bob.close()


def _has_coin(inventory: list[str]) -> bool:
    return "copper_coin" in inventory


def test_clock_updates_broadcast_to_players(
    simulation_server: SimulationServer,
) -> None:
    """Clock time_update messages are broadcast to all connected players (Sprint 15.1)."""
    asyncio.run(_test_clock_broadcast(simulation_server))


async def _test_clock_broadcast(server: SimulationServer) -> None:
    """Connected players should receive time_update broadcasts when the clock advances."""
    alice = await _connect(server, "alice")
    try:
        # Wait for a time_update broadcast. The clock advances every tick_seconds
        # (typically 1 second in tests), so we should see one within a few seconds.
        time_update = await alice.wait_for_broadcast("time_update", timeout=10)
        assert "hour" in time_update
        assert "minute" in time_update
        assert "day" in time_update
        assert "season" in time_update
        assert "weather" in time_update
        assert isinstance(time_update["hour"], int)
        assert 0 <= time_update["hour"] < 24
    finally:
        await alice.close()
