"""Cross-manager `DeliveryDirective` parity harness (Rust-port Phase 3a, gap 4).

`test_gateway_adapter.py` already proves `direct_reply` byte-identity between
the real `/ws` pipeline and the gateway adapter for a *single* connected
player (no room-mate ever exists to diverge on). That leaves the other half
of the 3a exit check unexercised: "the same set of `DeliveryDirective`s the
real `ConnectionManager` path produces today". This module closes that gap
with a two-player scenario.

Both players in the fixture (`player-1`/`ACTOR_ID`, `player-2`/`ROOMMATE_ID`)
come from the real seeded world content: `ensure_world_bootstrapped`
(`world/bootstrap.py`) unconditionally seeds a `player-2` at the same
`seed_player_start_room` as the primary seed player, on every worktree/CI run
-- no test-only world content invented here, per the repo's data-driven-config
rule.

The command under test is `say <text>`, chosen because it drives both
`broadcast_command_effects` fan-out shapes a room-mate (but never the actor)
receives in one invocation: the P2ROOM `chat_outbox` entry
(`ctx.tell_room_chat`, a `feed_append`/chat payload) and the always-on
post-command `state_change` nudge. Both are `RoomTarget` deliveries excluding
the actor -- exactly the shape `broadcast_command_effects` produces for the
vast majority of commands (narration + state_change), so proving parity here
generalizes past `say` itself.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lorecraft.config import Settings
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.gateway.adapter import GatewayAdapter, encode_frame, read_frame
from lorecraft.main import create_app
from lorecraft.protocol import PROTOCOL_VERSION
from lorecraft.protocol.envelope import CommandEnvelope
from lorecraft.protocol.gateway import (
    CommandReply,
    Connected,
    ConnectAck,
    DeliveryDirective,
    GatewayCommand,
    GlobalTarget,
    PlayerTarget,
    RoomTarget,
    gateway_outbound_from_json,
)
from lorecraft.state import AppState
from lorecraft.webui.player.ws_command import handle_ws_command
from tests.unit.test_connection_manager import _FakeSocket

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTOR_ID = "player-1"
# Unconditionally seeded by `ensure_world_bootstrapped` at the same
# `seed_player_start_room` as the primary seed player -- the real,
# data-driven two-occupant room this harness needs (see module docstring).
ROOMMATE_ID = "player-2"
COMMAND = "say hello there"


@pytest.fixture
def state(tmp_path: Path) -> Iterator[AppState]:
    """A fully-wired AppState with both seeded players in the same start room.

    Same shape as `test_gateway_adapter.py`'s `state` fixture (real seeded
    Ashmoore world content via `create_app`'s lifespan startup).
    """
    settings = Settings(
        database_path=str(tmp_path / "game.db"),
        audit_database_path=str(tmp_path / "audit.db"),
        world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml"),
        issues_yaml_path=str(tmp_path / "issues.yaml"),
        news_yaml_path=str(tmp_path / "news.yaml"),
        help_yaml_path=str(tmp_path / "help_topics.yaml"),
        admin_jwt_secret="test-admin-secret-at-least-32-bytes!!",
        seed_player_id=ACTOR_ID,
        seed_player_username=ACTOR_ID,
        # Freeze the world clock so the `time` snapshot in `updates` is
        # deterministic across the two parity runs (ratio 0 => no advance).
        world_time_ratio=0.0,
    )
    app = create_app(settings=settings)
    with TestClient(app):
        state: AppState = app.state.lorecraft
        yield state


def _envelope(session_id: str, command_id: str, raw: str) -> CommandEnvelope:
    return CommandEnvelope(
        protocol_version=PROTOCOL_VERSION,
        world_id="world",
        actor_id=ACTOR_ID,
        player_id=ACTOR_ID,
        session_id=session_id,
        command_id=command_id,
        receive_sequence=1,
        deadline_ms=1000,
        raw=raw,
    )


def _connect(adapter: GatewayAdapter, player_id: str) -> str:
    """Drive the adapter's `Connected` handshake for `player_id`, returning its
    minted session id (generalizes `test_gateway_adapter.py`'s
    `_connect_session` to an explicit player so both occupants can connect)."""
    frames = asyncio.run(adapter.handle_inbound(Connected(player_id=player_id)))
    ack = frames[0]
    assert isinstance(ack, ConnectAck)
    return ack.session_id


def _recipients(
    directive: DeliveryDirective, room_of: dict[str, str], connected: set[str]
) -> set[str]:
    """Resolve one directive's recipient set against a small, known two-player
    room/connection topology.

    This stands in for what Rust's `ConnectionRegistry` resolves a `target`/
    `exclude` pair against once it owns the authoritative connection map
    (Phase 3 decision 5) -- for a fixed two-player room, "who is a member and
    not excluded" is exactly that resolution, without needing a live Rust
    process (matches this harness's hermetic, single-process approach).
    """
    target = directive.target
    if isinstance(target, PlayerTarget):
        recipients = {target.id} if target.id in connected else set()
    elif isinstance(target, RoomTarget):
        recipients = {pid for pid, room in room_of.items() if room == target.id}
    elif isinstance(target, GlobalTarget):
        recipients = set(connected)
    else:  # pragma: no cover - exhaustive today; guards future target additions
        raise AssertionError(f"unknown delivery target: {target!r}")
    if directive.exclude is not None:
        recipients.discard(directive.exclude)
    return recipients


def test_room_broadcast_directive_parity_matches_real_connection_manager(
    state: AppState, tmp_path: Path
) -> None:
    """`say`'s room-visible fan-out is identical whether delivered by the real
    `ConnectionManager` straight to a room-mate's socket, or recorded as
    `DeliveryDirective`s by the adapter's `DirectiveConnectionManager` and
    resolved against the same two-player room -- and the actor's own reply is
    unaffected by which manager was injected.
    """
    start_room = state.settings.seed_player_start_room

    # --- Real `ConnectionManager` path: `_FakeSocket` doubles on both players.
    real_manager = ConnectionManager()
    actor_socket = _FakeSocket()
    roommate_socket = _FakeSocket()
    asyncio.run(real_manager.connect(ACTOR_ID, actor_socket, room_id=start_room))
    asyncio.run(real_manager.connect(ROOMMATE_ID, roommate_socket, room_id=start_room))

    real_reply = asyncio.run(
        handle_ws_command(state, real_manager, ACTOR_ID, "session-real", COMMAND)
    )

    # The actor's own confirmation is the function's return value, never a
    # send to their own socket -- true regardless of which manager is used.
    assert actor_socket.sent == []
    roommate_payloads = list(roommate_socket.sent)
    assert len(roommate_payloads) == 2, (
        "expected exactly the P2ROOM chat feed_append and the post-command "
        f"state_change; got {roommate_payloads!r}"
    )
    assert roommate_payloads[0]["message_type"] == "chat"
    assert roommate_payloads[1]["type"] == "state_change"

    # --- Adapter path: `DirectiveConnectionManager` over a real UDS socket. --
    adapter = GatewayAdapter(state, socket_path=str(tmp_path / "gateway.sock"))
    # Room-mate connects first (mirroring "already present"), then the actor,
    # whose minted session id is used to send the forwarded command.
    _connect(adapter, ROOMMATE_ID)
    actor_session = _connect(adapter, ACTOR_ID)

    async def _roundtrip() -> CommandReply:
        server = await adapter.start()
        try:
            reader, writer = await asyncio.open_unix_connection(
                path=adapter._socket_path  # pyright: ignore[reportPrivateUsage]
            )
            envelope = _envelope(actor_session, "c1", COMMAND)
            writer.write(encode_frame(GatewayCommand(envelope=envelope).to_json()))
            await writer.drain()
            raw = await read_frame(reader)
            assert raw is not None
            writer.close()
            await writer.wait_closed()
            outbound = gateway_outbound_from_json(raw)
            assert isinstance(outbound, CommandReply)
            return outbound
        finally:
            server.close()
            await server.wait_closed()

    adapter_reply = asyncio.run(_roundtrip())

    # The actor's own reply stays byte-identical between the two paths --
    # additional room occupants must not perturb it (extends the single-player
    # parity anchor in `test_gateway_adapter.py` to a two-player scenario).
    assert adapter_reply.direct_reply == real_reply

    # Resolve the adapter's directives against the same two-player room the
    # real manager used, and compare only what would reach the room-mate.
    room_of = {ACTOR_ID: start_room, ROOMMATE_ID: start_room}
    connected = {ACTOR_ID, ROOMMATE_ID}
    resolved_for_roommate = [
        directive.payload
        for directive in adapter_reply.deliveries
        if ROOMMATE_ID in _recipients(directive, room_of, connected)
    ]
    assert resolved_for_roommate == roommate_payloads

    # No directive would (incorrectly) also reach the actor themselves --
    # the real manager never sent them anything either (`actor_socket.sent`
    # above), so the two paths agree on that too.
    assert all(
        ACTOR_ID not in _recipients(directive, room_of, connected)
        for directive in adapter_reply.deliveries
    )
