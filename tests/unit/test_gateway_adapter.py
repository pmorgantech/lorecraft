"""Gateway adapter (Phase 3a): auth handoff, connect handshake, and the
command round-trip whose `direct_reply` must match the shared `/ws` pipeline.

The command test is the parity anchor the later Rust<->Python parity harness
builds on: a `Command` driven through the adapter (both directly and over a real
UDS round-trip) returns a `CommandReply` whose `direct_reply` is byte-identical
to what `handle_ws_command` produces for the same command.
"""

from __future__ import annotations

import asyncio
import os
import socket
import stat
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lorecraft.config import Settings
from lorecraft.gateway.adapter import (
    GatewayAdapter,
    GatewayPushManager,
    encode_frame,
    read_frame,
)
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.gateway.connection_manager import DirectiveConnectionManager
import lorecraft.main as main_mod
from lorecraft.main import create_app
from lorecraft.protocol import PROTOCOL_VERSION
from lorecraft.protocol.envelope import CommandEnvelope
from lorecraft.protocol.gateway import (
    AuthResult,
    ClientClose,
    Connected,
    ConnectAck,
    CommandReply,
    Deliver,
    DeliveryDirective,
    Disconnected,
    DisconnectAck,
    GatewayCommand,
    GatewayOutbound,
    GlobalTarget,
    GracefulQuit,
    PlayerTarget,
    RedeemTicket,
    RoomTarget,
    ValidateAdminToken,
    gateway_outbound_from_json,
)
from lorecraft.state import AppState
from lorecraft.webui.admin.auth import create_token
from lorecraft.webui.player.auth import issue_ws_ticket
from lorecraft.webui.player.ws_command import handle_ws_command

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYER_ID = "player-1"
SECOND_PLAYER_ID = "player-2"


def _base_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=str(tmp_path / "game.db"),
        audit_database_path=str(tmp_path / "audit.db"),
        world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml"),
        issues_yaml_path=str(tmp_path / "issues.yaml"),
        news_yaml_path=str(tmp_path / "news.yaml"),
        help_yaml_path=str(tmp_path / "help_topics.yaml"),
        admin_jwt_secret="test-admin-secret-at-least-32-bytes!!",
        seed_player_id=PLAYER_ID,
        seed_player_username=PLAYER_ID,
        # Freeze the world clock so the `time` snapshot in a command's `updates`
        # is deterministic between the two parity runs (ratio 0 => no advance).
        world_time_ratio=0.0,
        # Keep the lifespan-managed socket inside the test's tmp dir so a
        # gateway-enabled run never touches the repo's var/.
        gateway_socket_path=str(tmp_path / "lifespan-gateway.sock"),
    )


@pytest.fixture
def state(tmp_path: Path) -> Iterator[AppState]:
    """A fully-wired AppState with the seed player at the seeded start room.

    The AppState is built by `create_app`'s lifespan startup (world bootstrap +
    service wiring), so the fixture holds a `TestClient` context open for the
    duration of the test to run that lifespan and expose `app.state.lorecraft`.
    """
    app = create_app(settings=_base_settings(tmp_path))
    with TestClient(app):
        state: AppState = app.state.lorecraft
        yield state


@pytest.fixture
def adapter(state: AppState, tmp_path: Path) -> GatewayAdapter:
    return GatewayAdapter(state, socket_path=str(tmp_path / "gateway.sock"))


# --- auth handoff ----------------------------------------------------------


def test_redeem_ticket_valid_then_invalid(
    state: AppState, adapter: GatewayAdapter
) -> None:
    ticket = issue_ws_ticket(state, PLAYER_ID)

    (ok,) = asyncio.run(adapter.handle_inbound(RedeemTicket(ticket=ticket)))
    assert isinstance(ok, AuthResult)
    assert ok.accepted is True
    assert ok.player_id == PLAYER_ID

    # Single-use: the same ticket no longer redeems; a stolen/expired one fails.
    (reused,) = asyncio.run(adapter.handle_inbound(RedeemTicket(ticket=ticket)))
    assert isinstance(reused, AuthResult)
    assert reused.accepted is False
    assert reused.player_id is None


def test_validate_admin_token(state: AppState, adapter: GatewayAdapter) -> None:
    token = create_token(
        "e2e-admin", "superadmin", state.settings.admin_jwt_secret, 900, "access"
    )
    (ok,) = asyncio.run(adapter.handle_inbound(ValidateAdminToken(token=token)))
    assert isinstance(ok, AuthResult)
    assert ok.accepted is True
    assert ok.player_id is None  # admin tokens carry no player_id (see adapter)

    (bad,) = asyncio.run(adapter.handle_inbound(ValidateAdminToken(token="not-a-jwt")))
    assert isinstance(bad, AuthResult)
    assert bad.accepted is False


# --- connection lifecycle --------------------------------------------------


def test_connected_returns_connectack_and_player_joined_deliver(
    state: AppState, adapter: GatewayAdapter
) -> None:
    frames = asyncio.run(adapter.handle_inbound(Connected(player_id=PLAYER_ID)))
    ack = frames[0]
    assert isinstance(ack, ConnectAck)
    assert ack.room_id == state.settings.seed_player_start_room
    assert ack.session_id
    # The connecting client's own frame is a `connected` direct frame.
    first_direct = ack.direct_frames[0]
    assert isinstance(first_direct, dict)
    assert first_direct["type"] == "connected"

    # The room-facing `player_joined` broadcast is a standalone Deliver, not a
    # direct frame (it is for *other* occupants).
    delivers = [f for f in frames[1:] if isinstance(f, Deliver)]
    assert any(
        isinstance(d.directive.payload, dict)
        and d.directive.payload.get("type") == "player_joined"
        for d in delivers
    )
    # Mirror now knows the player and their session.
    assert adapter.manager.is_connected(PLAYER_ID)
    assert adapter.manager.session_of(PLAYER_ID) == ack.session_id


def test_graceful_quit_disconnect_skips_teardown(
    state: AppState, adapter: GatewayAdapter
) -> None:
    asyncio.run(adapter.handle_inbound(Connected(player_id=PLAYER_ID)))
    frames = asyncio.run(
        adapter.handle_inbound(Disconnected(player_id=PLAYER_ID, reason=GracefulQuit()))
    )
    # No flicker/player_left broadcasts on a graceful quit; mirror is cleared.
    # The terminal DisconnectAck is still emitted (and is the *only* frame) so
    # the Rust gateway's teardown handshake always completes — even when there is
    # nothing to fan out.
    assert frames == [DisconnectAck()]
    assert not adapter.manager.is_connected(PLAYER_ID)


def test_client_close_disconnect_emits_player_left(
    state: AppState, adapter: GatewayAdapter
) -> None:
    asyncio.run(adapter.handle_inbound(Connected(player_id=PLAYER_ID)))
    frames = asyncio.run(
        adapter.handle_inbound(Disconnected(player_id=PLAYER_ID, reason=ClientClose()))
    )
    payload_types = {
        d.directive.payload.get("type")
        for d in frames
        if isinstance(d, Deliver) and isinstance(d.directive.payload, dict)
    }
    assert "player_left" in payload_types
    # The teardown fan-out `Deliver`s must precede the terminal `DisconnectAck`:
    # Rust dispatches the leave to remaining players as the frames arrive and only
    # drops the link on the ack, so ordering (Delivers first, ack last) is the
    # load-bearing contract.
    assert isinstance(frames[-1], DisconnectAck)
    assert not any(isinstance(f, DisconnectAck) for f in frames[:-1])
    assert not adapter.manager.is_connected(PLAYER_ID)


# --- command round-trip (the parity anchor) --------------------------------


def _envelope(session_id: str, command_id: str, raw: str) -> CommandEnvelope:
    return CommandEnvelope(
        protocol_version=PROTOCOL_VERSION,
        world_id="world",
        actor_id=PLAYER_ID,
        player_id=PLAYER_ID,
        session_id=session_id,
        command_id=command_id,
        receive_sequence=1,
        deadline_ms=1000,
        raw=raw,
    )


def _warm_up_look(adapter: GatewayAdapter, session_id: str) -> None:
    """Run one `look` so first-look state mutations (visited/discovered/met)
    settle — subsequent looks are then idempotent, making the parity compare
    deterministic."""
    asyncio.run(
        adapter.handle_inbound(
            GatewayCommand(envelope=_envelope(session_id, "warmup", "look"))
        )
    )


def _connect_session(adapter: GatewayAdapter) -> str:
    frames = asyncio.run(adapter.handle_inbound(Connected(player_id=PLAYER_ID)))
    ack = frames[0]
    assert isinstance(ack, ConnectAck)
    return ack.session_id


def _expected_look_reply(state: AppState, session_id: str) -> dict[str, object]:
    # A throwaway manager keeps the baseline's fan-out out of the adapter's buffer.
    return asyncio.run(
        handle_ws_command(
            state, DirectiveConnectionManager(), PLAYER_ID, session_id, "look"
        )
    )


def test_command_reply_direct_reply_matches_shared_pipeline(
    state: AppState, adapter: GatewayAdapter
) -> None:
    session_id = _connect_session(adapter)
    _warm_up_look(adapter, session_id)
    expected = _expected_look_reply(state, session_id)

    frames = asyncio.run(
        adapter.handle_inbound(
            GatewayCommand(envelope=_envelope(session_id, "c1", "look"))
        )
    )
    (command_reply,) = frames
    assert isinstance(command_reply, CommandReply)
    assert command_reply.command_id == "c1"
    assert isinstance(command_reply.direct_reply, dict)
    assert command_reply.direct_reply["type"] == "command_result"
    assert command_reply.direct_reply == expected


def test_command_round_trips_over_real_uds_socket(
    state: AppState, adapter: GatewayAdapter
) -> None:
    session_id = _connect_session(adapter)
    _warm_up_look(adapter, session_id)
    expected = _expected_look_reply(state, session_id)

    async def _roundtrip() -> CommandReply:
        server = await adapter.start()
        try:
            reader, writer = await asyncio.open_unix_connection(
                path=adapter._socket_path  # pyright: ignore[reportPrivateUsage]
            )
            envelope = _envelope(session_id, "c2", "look")
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

    reply = asyncio.run(_roundtrip())
    assert reply.command_id == "c2"
    assert reply.direct_reply == expected


# --- app-lifespan wiring (Phase 3b, flag-gated) ------------------------------


def test_lifespan_gateway_disabled_by_default(tmp_path: Path) -> None:
    """With `gateway_enabled` off (the default) the app must behave exactly as
    before: no adapter constructed, no UDS socket created."""
    settings = _base_settings(tmp_path)
    assert settings.gateway_enabled is False
    app = create_app(settings=settings)
    with TestClient(app):
        assert app.state.gateway_adapter is None
        assert not Path(settings.gateway_socket_path).exists()


def test_lifespan_gateway_enabled_starts_uds_with_owner_only_perms(
    tmp_path: Path,
) -> None:
    """`gateway_enabled=True` starts the adapter's UDS listener at startup
    (0600 — an unauthenticated internal channel must be owner-only) and
    unlinks the socket file at shutdown."""
    settings = replace(_base_settings(tmp_path), gateway_enabled=True)
    app = create_app(settings=settings)
    sock_path = Path(settings.gateway_socket_path)
    with TestClient(app):
        assert isinstance(app.state.gateway_adapter, GatewayAdapter)
        mode = os.lstat(sock_path).st_mode
        assert stat.S_ISSOCK(mode)
        assert stat.S_IMODE(mode) == 0o600
    # Lifespan shutdown stopped the adapter and removed the socket file.
    assert not sock_path.exists()


def test_gateway_mode_routes_autonomous_broadcasts_through_push_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard: in gateway mode the autonomous (server-initiated) broadcasters — the
    world clock's `time_update` and weather narration — must be wired to the
    `GatewayPushManager`, NOT the raw `ConnectionManager` (whose socket pool is
    empty in gateway mode, since clients live in Rust's authoritative registry).
    If a future autonomous broadcaster is wired straight to `manager` in gateway
    mode its pushes would silently vanish; this fails loudly instead.

    Scope note (known-incomplete, to be listed in the Rust migration/scripting
    docs): the clock and weather handlers both consume the *single*
    `broadcast_manager` local in `create_app`, so capturing the manager handed to
    `register_weather_handlers` proves the shared selection for both. Other
    autonomous emitters wired independently later (e.g. NPC ambient emotes) are
    not each asserted here — extend this guard when one lands.
    """
    captured: dict[str, object] = {}
    real = main_mod.register_weather_handlers

    def _capture(
        bus: object, engine: object, manager: object, *a: object, **kw: object
    ):  # type: ignore[no-untyped-def]
        captured["manager"] = manager
        return real(bus, engine, manager, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(main_mod, "register_weather_handlers", _capture)

    off_dir = tmp_path / "off"
    off_dir.mkdir()
    on_dir = tmp_path / "on"
    on_dir.mkdir()

    # Flag OFF (rollback / legacy `/ws`): the raw ConnectionManager, unchanged.
    with TestClient(create_app(settings=_base_settings(off_dir))):
        assert isinstance(captured["manager"], ConnectionManager)

    captured.clear()

    # Flag ON (gateway cutover): the late-bound push manager that relays
    # autonomous broadcasts to Rust as standalone `Deliver` frames.
    on_settings = replace(_base_settings(on_dir), gateway_enabled=True)
    with TestClient(create_app(settings=on_settings)):
        assert isinstance(captured["manager"], GatewayPushManager)


# --- UDS hardening in start()/stop() -----------------------------------------


def test_start_unlinks_stale_socket_left_by_prior_crash(
    state: AppState, tmp_path: Path
) -> None:
    stale_path = tmp_path / "stale-gateway.sock"
    # A crashed process leaves the bound socket file behind on disk.
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(stale_path))
    stale.close()
    assert stale_path.exists()

    adapter = GatewayAdapter(state, socket_path=str(stale_path))

    async def _cycle() -> None:
        await adapter.start()  # must not fail with "Address already in use"
        assert stale_path.is_socket()
        await adapter.stop()

    asyncio.run(_cycle())
    assert not stale_path.exists()  # stop() cleaned up after itself


def test_start_refuses_to_unlink_a_non_socket_path(
    state: AppState, tmp_path: Path
) -> None:
    """A misconfigured socket path pointing at a real file must never be
    destroyed — start() raises instead of unlinking."""
    precious = tmp_path / "not-a-socket"
    precious.write_text("do not delete")
    adapter = GatewayAdapter(state, socket_path=str(precious))
    with pytest.raises(RuntimeError, match="not a socket"):
        asyncio.run(adapter.start())
    assert precious.read_text() == "do not delete"


def test_start_creates_missing_parent_dir(state: AppState, tmp_path: Path) -> None:
    """`var/` may not exist in a fresh checkout — start() creates the parent."""
    sock_path = tmp_path / "missing-var" / "gateway.sock"
    adapter = GatewayAdapter(state, socket_path=str(sock_path))

    async def _cycle() -> None:
        await adapter.start()
        assert sock_path.is_socket()
        await adapter.stop()

    asyncio.run(_cycle())


# --- follow-break on involuntary disconnect (wired in 3b) --------------------


def test_client_close_breaks_follow_and_notifies_target(
    state: AppState, adapter: GatewayAdapter
) -> None:
    """A follower's involuntary drop clears the follow graph and delivers the
    "no longer following you" notice + players-online nudge to the target as
    Player-targeted `Deliver` directives. `player-2` is the second dev player
    the world bootstrap already seeds at the same start room."""
    follower_id = SECOND_PLAYER_ID
    asyncio.run(adapter.handle_inbound(Connected(player_id=PLAYER_ID)))
    asyncio.run(adapter.handle_inbound(Connected(player_id=follower_id)))
    follow = state.services.follow
    assert follow is not None
    follow._following[follower_id] = PLAYER_ID  # Bryn follows player-1

    frames = asyncio.run(
        adapter.handle_inbound(
            Disconnected(player_id=follower_id, reason=ClientClose())
        )
    )

    assert follow.target_of(follower_id) is None  # graph cleared
    to_target = [
        f.directive
        for f in frames
        if isinstance(f, Deliver)
        and isinstance(f.directive.target, PlayerTarget)
        and f.directive.target.id == PLAYER_ID
    ]
    feed = [
        d.payload
        for d in to_target
        if isinstance(d.payload, dict) and d.payload.get("type") == "feed_append"
    ]
    assert feed and "no longer following you" in str(feed[0]["content"])
    assert any(
        isinstance(d.payload, dict) and d.payload.get("type") == "state_change"
        for d in to_target
    )


def test_target_client_close_breaks_follow_and_notifies_follower(
    state: AppState, adapter: GatewayAdapter
) -> None:
    """The mirror case: the followed player drops; the still-connected follower
    is orphaned and told the target left."""
    follower_id = SECOND_PLAYER_ID
    asyncio.run(adapter.handle_inbound(Connected(player_id=PLAYER_ID)))
    asyncio.run(adapter.handle_inbound(Connected(player_id=follower_id)))
    follow = state.services.follow
    assert follow is not None
    follow._following[follower_id] = PLAYER_ID

    frames = asyncio.run(
        adapter.handle_inbound(Disconnected(player_id=PLAYER_ID, reason=ClientClose()))
    )

    assert follow.followers_of(PLAYER_ID) == []
    notices = [
        f.directive.payload
        for f in frames
        if isinstance(f, Deliver)
        and isinstance(f.directive.target, PlayerTarget)
        and f.directive.target.id == follower_id
        and isinstance(f.directive.payload, dict)
        and f.directive.payload.get("type") == "feed_append"
    ]
    assert notices and "You stop following" in str(notices[0]["content"])


# --- drain-lock discipline ----------------------------------------------------


def test_lifecycle_and_command_drains_do_not_cross_contaminate(
    state: AppState, adapter: GatewayAdapter
) -> None:
    """A command and a lifecycle event handled concurrently must each drain only
    their own directives: the command's fan-out never leaks into the lifecycle's
    `Deliver`s, and the connect's `player_joined` never leaks into the
    `CommandReply.deliveries` (both run whole under the directive lock)."""
    second_id = SECOND_PLAYER_ID
    session_id = _connect_session(adapter)  # PLAYER_ID online
    _warm_up_look(adapter, session_id)

    async def _run() -> tuple[list[GatewayOutbound], list[GatewayOutbound]]:
        command_frames, lifecycle_frames = await asyncio.gather(
            adapter.handle_inbound(
                GatewayCommand(envelope=_envelope(session_id, "cc", "say hello"))
            ),
            adapter.handle_inbound(Connected(player_id=second_id)),
        )
        return command_frames, lifecycle_frames

    command_frames, lifecycle_frames = asyncio.run(_run())

    (reply,) = command_frames
    assert isinstance(reply, CommandReply)
    command_types = {
        d.payload.get("type") for d in reply.deliveries if isinstance(d.payload, dict)
    }
    assert "player_joined" not in command_types  # lifecycle didn't leak in

    ack, *delivers = lifecycle_frames
    assert isinstance(ack, ConnectAck)
    lifecycle_types = {
        f.directive.payload.get("type")
        for f in delivers
        if isinstance(f, Deliver) and isinstance(f.directive.payload, dict)
    }
    assert lifecycle_types == {"player_joined"}  # nothing of the command leaked


# --- autonomous push (clock/weather Deliver relay) ---------------------------


async def _await_link(adapter: GatewayAdapter) -> None:
    """Wait until the adapter has registered one accepted client link."""
    for _ in range(200):
        if adapter._links:  # pyright: ignore[reportPrivateUsage]
            return
        await asyncio.sleep(0.005)
    raise AssertionError("adapter never registered the client link")


def test_push_deliver_writes_deliver_frame_to_active_link(
    state: AppState, tmp_path: Path
) -> None:
    """An autonomous `push_deliver` reaches an active link as a `Deliver` frame
    carrying the directive verbatim (the clock/weather relay path)."""

    async def scenario() -> None:
        adapter = GatewayAdapter(state, socket_path=str(tmp_path / "push.sock"))
        await adapter.start()
        try:
            reader, writer = await asyncio.open_unix_connection(
                str(tmp_path / "push.sock")
            )
            await _await_link(adapter)
            directive = DeliveryDirective(
                target=GlobalTarget(),
                exclude=None,
                payload={"type": "time_update", "hour": 7},
            )
            await adapter.push_deliver(directive)

            raw = await asyncio.wait_for(read_frame(reader), timeout=2)
            assert raw is not None
            frame = gateway_outbound_from_json(raw)
            assert isinstance(frame, Deliver)
            assert isinstance(frame.directive.target, GlobalTarget)
            assert frame.directive.payload == {"type": "time_update", "hour": 7}
            writer.close()
            await writer.wait_closed()
        finally:
            await adapter.stop()

    asyncio.run(scenario())


def test_push_deliver_no_active_connections_is_noop(
    state: AppState, tmp_path: Path
) -> None:
    """With zero active links, `push_deliver` is a harmless no-op — nobody is
    connected through the gateway to receive the broadcast."""

    async def scenario() -> None:
        adapter = GatewayAdapter(state, socket_path=str(tmp_path / "noop.sock"))
        await adapter.start()
        try:
            assert not adapter._links  # pyright: ignore[reportPrivateUsage]
            # Must not raise, must not block.
            await adapter.push_deliver(
                DeliveryDirective(
                    target=GlobalTarget(), exclude=None, payload={"type": "time_update"}
                )
            )
        finally:
            await adapter.stop()

    asyncio.run(scenario())


def test_push_deliver_and_reply_never_corrupt_frames(
    state: AppState, tmp_path: Path
) -> None:
    """Concurrent autonomous pushes and a command-lifecycle reply share one
    single-writer queue, so no two writes ever interleave on the `StreamWriter`:
    every frame read back decodes cleanly and the counts are exact."""

    async def scenario() -> None:
        sock = str(tmp_path / "sync.sock")
        adapter = GatewayAdapter(state, socket_path=sock)
        await adapter.start()
        try:
            reader, writer = await asyncio.open_unix_connection(sock)
            await _await_link(adapter)

            # Drive a Connected handshake (reply path: ConnectAck + one
            # player_joined Deliver) and five autonomous pushes concurrently
            # through the shared per-connection writer.
            writer.write(encode_frame(Connected(player_id=PLAYER_ID).to_json()))
            await writer.drain()
            await asyncio.gather(
                *[
                    adapter.push_deliver(
                        DeliveryDirective(
                            target=GlobalTarget(),
                            exclude=None,
                            payload={"type": "time_update", "n": i},
                        )
                    )
                    for i in range(5)
                ]
            )

            frames: list[GatewayOutbound] = []
            for _ in range(7):  # 1 ConnectAck + 1 connect Deliver + 5 pushes
                raw = await asyncio.wait_for(read_frame(reader), timeout=2)
                assert raw is not None
                frames.append(gateway_outbound_from_json(raw))

            acks = [f for f in frames if isinstance(f, ConnectAck)]
            delivers = [f for f in frames if isinstance(f, Deliver)]
            assert len(acks) == 1
            assert len(delivers) == 6  # one player_joined + five time_update pushes
            pushed = [
                d.directive.payload
                for d in delivers
                if isinstance(d.directive.payload, dict)
                and d.directive.payload.get("type") == "time_update"
            ]
            assert len(pushed) == 5
            writer.close()
            await writer.wait_closed()
        finally:
            await adapter.stop()

    asyncio.run(scenario())


class _CapturingAdapter:
    """A stand-in for `GatewayAdapter` that captures pushed directives and
    exposes a real `DirectiveConnectionManager` mirror for selection."""

    def __init__(self) -> None:
        self.manager = DirectiveConnectionManager()
        self.pushed: list[DeliveryDirective] = []

    async def push_deliver(self, directive: DeliveryDirective) -> None:
        self.pushed.append(directive)


def test_gateway_push_manager_maps_broadcasts_like_directive_manager() -> None:
    """The push wrapper builds the exact same `DeliveryDirective` wire shapes as
    the command-path `DirectiveConnectionManager`, and flushes via `push_deliver`."""
    fake = _CapturingAdapter()
    wrapper = GatewayPushManager()
    wrapper.bind(fake)  # type: ignore[arg-type]

    async def via_wrapper() -> None:
        await wrapper.broadcast_global({"type": "time_update"})
        await wrapper.broadcast_to_room("tavern", {"type": "x"}, exclude="p1")
        await wrapper.send_to_player("p2", {"type": "y"})

    asyncio.run(via_wrapper())

    baseline = DirectiveConnectionManager()

    async def via_baseline() -> None:
        await baseline.broadcast_global({"type": "time_update"})
        await baseline.broadcast_to_room("tavern", {"type": "x"}, exclude="p1")
        await baseline.send_to_player("p2", {"type": "y"})

    asyncio.run(via_baseline())

    # Byte-identical wire shapes to the command path (target + exclude + payload).
    assert [d.to_json() for d in fake.pushed] == [
        d.to_json() for d in baseline.deliveries
    ]
    assert isinstance(fake.pushed[0].target, GlobalTarget)
    assert isinstance(fake.pushed[1].target, RoomTarget)
    assert isinstance(fake.pushed[2].target, PlayerTarget)


def test_gateway_push_manager_selection_delegates_to_mirror() -> None:
    """Selection answers from the adapter's connection mirror so a world-level
    broadcast filters to rooms with an actual gateway audience."""
    fake = _CapturingAdapter()
    wrapper = GatewayPushManager()
    wrapper.bind(fake)  # type: ignore[arg-type]
    fake.manager.mark_connected("p1", "tavern")

    assert wrapper.occupied_rooms() == ["tavern"]
    assert wrapper.players_in_room("tavern") == ["p1"]
    assert wrapper.connected_player_ids() == ["p1"]
    assert wrapper.is_connected("p1") is True


def test_gateway_push_manager_unbound_is_noop() -> None:
    """Before the adapter is bound (startup window) delivery is a no-op and
    selection is empty — no audience exists yet."""
    wrapper = GatewayPushManager()
    asyncio.run(wrapper.broadcast_global({"type": "time_update"}))  # must not raise
    assert wrapper.occupied_rooms() == []
    assert wrapper.players_in_room("tavern") == []
    assert wrapper.connected_player_ids() == []
    assert wrapper.is_connected("p1") is False
