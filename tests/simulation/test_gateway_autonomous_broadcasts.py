"""Gateway-fronted autonomous broadcast regression (Phase 3, GAP #3).

The timer/scheduler/event-driven broadcasters — autonomous NPC roam/patrol
narration, quest-timer expiries, traveling storm fronts, transit vehicle
departures — used to target the raw ``ConnectionManager``. That manager's socket
pool is EMPTY in gateway mode (clients live in Rust's authoritative registry, not
this process's pool), so those server-initiated broadcasts never reached
gateway-connected clients. GAP #3 rerouted every one of them through the
gateway-aware ``broadcast_manager`` (the ``GatewayPushManager`` in gateway mode,
the real manager when the flag is off).

This exercises the NPC-behavior path — the most deterministically triggerable of
the five, since ``NpcBehaviorService`` ticks on every ``TIME_ADVANCED`` event and
the world clock advances roughly once per real second in tests (the same cadence
the ``time_update`` clock test relies on). A patrol NPC is injected into the
disposable world DB with the connected player's room as its next stop; its
autonomous "arrives" narration must reach that player.

Through the Rust front door (``LORECRAFT_THROUGH_RUST=1``) this is the real
regression guard: pre-fix the narration went to the empty real manager and never
crossed to Rust, so the wait below timed out. Python-direct mode (flag off)
exercises the same assertion against the real ``ConnectionManager`` — whose pool
*does* hold the ``/ws``-connected player — so it always passed; the miss only ever
manifested in gateway mode, exactly like the gap-1 mover-registry regression.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlmodel import Session, create_engine, select

from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import NPC, Room
from tests.simulation.conftest import SimulationServer
from tests.simulation.virtual_player import VirtualPlayer

pytestmark = pytest.mark.simulation


def _username(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _inject_patrol_npc(server: SimulationServer, dest_room_id: str, name: str) -> str:
    """Insert a patrol NPC whose next stop is ``dest_room_id`` and return its id.

    ``patrol`` is deterministic (unlike ``wander``, which rolls the seedable RNG
    over exits): the NPC walks its ``route`` in order, ignoring adjacency, so its
    first move on the next tick is guaranteed to be into ``dest_room_id``. It
    starts in a *different* real room (any one but the destination — chosen from
    the DB, never hardcoded) so that first move is a genuine arrival there.
    ``move_every=1`` moves it on every tick, so the arrival lands within a couple
    of clock ticks.
    """
    engine = create_engine(
        f"sqlite:///{server.game_db_path}", connect_args={"timeout": 30}
    )
    with Session(engine) as session:
        start_room_id = session.exec(
            select(Room.id).where(Room.id != dest_room_id).limit(1)
        ).first()
        assert start_room_id is not None, "world needs a second room to patrol from"
        npc_id = f"gap3_patrol_{uuid.uuid4().hex[:8]}"
        session.add(
            NPC(
                id=npc_id,
                name=name,
                description="A test patrol NPC for the GAP #3 regression.",
                current_room_id=start_room_id,
                home_room_id=start_room_id,
                dialogue_tree_id="",
                ai={
                    "mode": "patrol",
                    "move_every": 1,
                    "route": [dest_room_id, start_room_id],
                },
            )
        )
        session.commit()
    engine.dispose()
    return npc_id


def _room_of(server: SimulationServer, player_id: str) -> str:
    engine = create_engine(f"sqlite:///{server.game_db_path}")
    try:
        with Session(engine) as session:
            player = session.get(Player, player_id)
            assert player is not None
            return player.current_room_id
    finally:
        engine.dispose()


async def _wait_for_named_feed(
    player: VirtualPlayer, needle: str, *, timeout: float
) -> dict[str, object]:
    """Block until a ``feed_append`` whose content mentions ``needle`` arrives.

    Idle-room feed narration in a single-player scenario comes only from the
    autonomous NPC tick, but filter on the unique NPC name anyway so the assertion
    can never be satisfied by an unrelated broadcast.
    """

    async def _wait() -> dict[str, object]:
        while True:
            message = await player.wait_for_broadcast("feed_append", timeout=timeout)
            if needle in str(message.get("content", "")):
                return message

    return await asyncio.wait_for(_wait(), timeout=timeout)


def test_autonomous_npc_narration_reaches_gateway_player(
    simulation_server: SimulationServer,
) -> None:
    asyncio.run(_test_autonomous_npc_narration(simulation_server))


async def _test_autonomous_npc_narration(server: SimulationServer) -> None:
    username = _username("watcher")
    player_id, ticket = server.prepare_login(username)
    # The freshly created character's spawn room is the patrol destination; the
    # NPC is injected before the socket opens so it is present for the very first
    # tick after connect.
    dest_room = _room_of(server, player_id)
    npc_name = f"Patrol Sentinel {uuid.uuid4().hex[:6]}"
    _inject_patrol_npc(server, dest_room, npc_name)

    watcher = await VirtualPlayer.connect(
        server.ws_url, player_id, username, ticket=ticket
    )
    try:
        # The clock ticks ~once per real second (same cadence as the time_update
        # test); the NPC patrols into `dest_room` on a tick and narrates its
        # arrival there. That autonomous broadcast only reaches this
        # gateway-connected watcher because GAP #3 routes it through
        # `broadcast_manager` — pre-fix (Rust-fronted) it hit the empty real
        # manager and this wait timed out.
        arrival = await _wait_for_named_feed(watcher, npc_name, timeout=20)
        assert arrival["message_type"] == "room_event"
        assert "arrives" in str(arrival["content"]).lower()
    finally:
        await watcher.close()
