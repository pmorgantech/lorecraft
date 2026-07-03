"""Multi-player scripted scenarios over real WebSockets (Sprint 12).

These complement the single-connection ASGI-transport integration tests
(`tests/integration/test_admin_websocket.py` et al.) with scenarios that only
show up once *multiple real* players are connected concurrently: room
broadcast fan-out on connect, and contention over a single shared item.

Note: the raw `/ws` command loop (`main.py::_handle_websocket_command`)
currently only returns `room_messages` to the *acting* player — unlike the
HTMX `POST /command` path, it does not yet re-broadcast them to other
WS-connected occupants of the room. That gap is tracked by roadmap Sprint 14
(unify the `/ws` and `/command` lifecycles), so these scenarios stick to
behavior the `/ws` protocol already guarantees today: the `player_joined`
broadcast on connect, and each player's own direct `command_result` replies.
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
