"""Python gateway adapter — the UDS listener for the Rust-port gateway (Phase 3).

Runs an `asyncio` Unix-domain-socket server speaking length-prefixed JSON
(4-byte big-endian length + UTF-8 JSON). The Rust gateway owns client sockets and
forwards framed `GatewayInbound` messages; this adapter dispatches them to the
*existing* Python credential/session/command logic and replies with framed
`GatewayOutbound` messages:

- `RedeemTicket`  -> `consume_ws_ticket`        -> `AuthResult`
- `ValidateAdminToken` -> admin `decode_token`  -> `AdminAuthResult`
- `Connected`     -> session boot/resume        -> `ConnectAck` (+ `Deliver`s)
- `Disconnected`  -> grace/flicker/player_left teardown -> `Deliver`s
- `Command`       -> shared `handle_ws_command`  -> `CommandReply`
- `BuildSnapshot` -> `build_look_request`        -> `SnapshotReady` (Phase 4)
- `ApplyOutcome`  -> `apply_outcome` (persist+commit) -> `OutcomeApplied` (Phase 4)

Fan-out is not sent to sockets here: a `DirectiveConnectionManager` records each
broadcast as a `DeliveryDirective`, which the adapter relays to Rust (Rust owns
the authoritative connection map and resolves recipients).

Wired into the app lifespan behind ``Settings.gateway_enabled`` (Phase 3b):
`main.py` starts/stops the adapter alongside the app when the flag is on, and
the existing Python `/ws` route stays registered either way as the rollback
path (design decision 8).
Composition/web-host layer: imports engine + features + web hosts, never
imported *by* `engine/`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import stat
from pathlib import Path

import jwt
from sqlmodel import Session

from lorecraft.gateway.coalescing import coalesce_key_for
from lorecraft.gateway.connection_manager import DirectiveConnectionManager
from lorecraft.gateway.effect_apply import apply_outcome
from lorecraft.gateway.snapshots import build_look_request
from lorecraft.protocol.envelope import CommandEnvelope, CommandId
from lorecraft.protocol.gateway import (
    AdminAuthResult,
    AdminTarget,
    ApplyOutcome,
    AuthResult,
    BuildSnapshot,
    ClientClose,
    Connected,
    ConnectAck,
    CommandReply,
    Deliver,
    DeliveryDirective,
    Disconnected,
    DisconnectAck,
    ExecutionRejected,
    GatewayCommand,
    GatewayInbound,
    GatewayOutbound,
    GlobalTarget,
    MovePlayer,
    OutcomeApplied,
    PlayerTarget,
    RedeemTicket,
    RoomTarget,
    SnapshotReady,
    ValidateAdminToken,
    gateway_inbound_from_json,
)
from lorecraft.errors import ValidationError
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.save import SessionSafetyService
from lorecraft.state import AppState
from lorecraft.types import JsonObject, JsonValue
from lorecraft.webui.admin.auth import decode_token
from lorecraft.webui.player.auth import consume_ws_ticket
from lorecraft.webui.player.messages import (
    EXECUTION_ERROR_MESSAGE,
    FROZEN_SESSION_MESSAGE,
)
from lorecraft.webui.player.ui_snapshots import (
    player_ui_updates,
    reconnect_sync_payload,
)
from lorecraft.webui.player.ws_command import handle_ws_command

log = logging.getLogger(__name__)

_LENGTH_PREFIX_BYTES = 4

# Hard cap on in-flight `BuildSnapshot` envelopes awaiting their correlated
# `ApplyOutcome`. Normally at most one command is outstanding per connection, so
# `_pending` holds a tiny handful; this cap only trips on genuine leakage — a
# Rust `execute_timeout_ms` elapsing (Rust cancels on its side and sends Python
# nothing) or a dropped `ApplyOutcome`. Combined with the per-player sweep on
# `Disconnected`, it bounds `_pending` so a leaked entry can never accumulate
# without limit. Oldest (insertion-order) entries are evicted first.
_MAX_PENDING_OUTCOMES = 1024


def _execution_error_reply() -> JsonObject:
    """The client-facing in-game error reply for a failed Phase 4 persistence handler.

    Mirrors the crash-capture payload the pure-Python command path degrades to
    (`handle_ws_command`'s `except` branch), so a `build_look_request`/`apply_outcome`
    fault surfaces to the player as a clean in-game error rather than a dropped
    socket. Carried on an `ExecutionRejected` frame back to Rust.
    """
    return {
        "type": "error",
        "message": EXECUTION_ERROR_MESSAGE,
    }


def encode_frame(payload: JsonValue) -> bytes:
    """Serialize a JSON value as a length-prefixed transport frame.

    Plain (non-canonical) JSON: the gateway channel only needs valid interchange,
    not the float-free canonical form used for replay hashing.
    """
    data = json.dumps(payload).encode("utf-8")
    return len(data).to_bytes(_LENGTH_PREFIX_BYTES, "big") + data


async def read_frame(reader: asyncio.StreamReader) -> JsonObject | None:
    """Read one length-prefixed frame, or return None at clean end-of-stream."""
    header = await reader.readexactly(_LENGTH_PREFIX_BYTES)
    length = int.from_bytes(header, "big")
    body = await reader.readexactly(length)
    decoded = json.loads(body.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("gateway frame is not a JSON object")
    return decoded


class _ClientLink:
    """One accepted UDS connection to the Rust peer.

    Both request→reply frames and autonomous `push_deliver` frames are enqueued
    on `outbound` and written by a single dedicated writer task, so no two
    coroutines ever write the underlying `StreamWriter` concurrently.
    """

    __slots__ = ("writer", "outbound")

    def __init__(self, writer: asyncio.StreamWriter) -> None:
        self.writer = writer
        self.outbound: asyncio.Queue[GatewayOutbound] = asyncio.Queue()


class GatewayAdapter:
    """Length-prefixed-JSON UDS server dispatching `GatewayInbound` frames."""

    def __init__(
        self,
        state: AppState,
        *,
        manager: DirectiveConnectionManager | None = None,
        socket_path: str | None = None,
    ) -> None:
        self._state = state
        # One mirror of all connections is shared across the (single) Rust peer
        # link; per Phase 3 decision 5 it is advisory for recipient selection.
        self._manager = manager or DirectiveConnectionManager()
        self._socket_path = socket_path or state.settings.gateway_socket_path
        # Drain discipline: the `DirectiveConnectionManager` records every
        # broadcast into ONE shared `deliveries` buffer, so any handler that
        # records directives and then `drain()`s (commands AND the
        # connect/disconnect lifecycle handlers) must run whole under this lock.
        # It is acquired once, at the `handle_inbound` dispatch level — see the
        # comment there for the interleaving hazard it prevents.
        self._directive_lock = asyncio.Lock()
        self._server: asyncio.AbstractServer | None = None
        # Currently-active client links (one per accepted UDS connection). Used
        # by `push_deliver` to relay an autonomous, server-initiated broadcast to
        # the Rust peer down a single link (Rust fans out from its own registry).
        self._links: set[_ClientLink] = set()
        # Phase 4 execution round-trip (Option A): the in-flight envelope from each
        # `BuildSnapshot`, keyed by `command_id`, so the correlated `ApplyOutcome`
        # (which carries only `command_id` + outcome, not the envelope) can recover
        # the player/session/raw needed to persist and build the reply. Removed on
        # `ApplyOutcome`. We keep the envelope here rather than widening the
        # protocol frame (the envelope is already in hand at BuildSnapshot time).
        self._pending: dict[CommandId, CommandEnvelope] = {}

    @property
    def manager(self) -> DirectiveConnectionManager:
        return self._manager

    # -- server lifecycle ---------------------------------------------------

    async def start(self) -> asyncio.AbstractServer:
        path = Path(self._socket_path)
        # `var/` may not exist in a fresh checkout — create the parent like the
        # rest of the app does for its runtime files (mkdir parents, exist_ok).
        path.parent.mkdir(parents=True, exist_ok=True)
        self._remove_stale_socket(path)
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=self._socket_path
        )
        # Owner-only: this is an intentionally-unauthenticated internal channel
        # (design decision 2 — UDS is localhost-confined), so a local non-owner
        # user must not be able to connect and impersonate players.
        os.chmod(self._socket_path, 0o600)
        log.info("gateway adapter listening on %s", self._socket_path)
        return self._server

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            # Don't leave a stale socket file behind for the next start to
            # trip over (Python < 3.13 asyncio does not unlink it on close).
            with contextlib.suppress(FileNotFoundError):
                os.unlink(self._socket_path)

    @staticmethod
    def _remove_stale_socket(path: Path) -> None:
        """Unlink a stale socket file left by a prior crash, and nothing else.

        Without this, a restart after an unclean shutdown fails to bind with
        `Address already in use`. Guard: only a socket file is ever unlinked —
        any other filesystem object at the configured path is a misconfiguration
        we must not destroy, so raise instead. `lstat` (not `stat`) so a symlink
        pointing at a socket is not mistaken for the socket itself.
        """
        try:
            mode = os.lstat(path).st_mode
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(mode):
            raise RuntimeError(
                f"gateway socket path {path} exists and is not a socket; "
                "refusing to unlink it — check LORECRAFT_GATEWAY_SOCKET_PATH"
            )
        log.warning("removing stale gateway socket %s", path)
        path.unlink()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        # A single dedicated writer task per connection drains `link.outbound`, so
        # the request→reply frames enqueued below and the autonomous frames
        # `push_deliver` enqueues never write the `StreamWriter` concurrently —
        # the admin-console per-connection queue+writer precedent
        # (webui/admin/websocket.py). The link is tracked for `push_deliver` for
        # exactly as long as the connection is served.
        link = _ClientLink(writer)
        self._links.add(link)
        sender = asyncio.create_task(self._drain_outbound(link))
        try:
            while True:
                try:
                    raw = await read_frame(reader)
                except asyncio.IncompleteReadError:
                    break  # peer closed the stream
                if raw is None:
                    break
                try:
                    inbound = gateway_inbound_from_json(raw)
                    outbound = await self.handle_inbound(inbound)
                except Exception:
                    # A malformed frame or a handler fault must not take the whole
                    # link down; log with traceback and keep serving other frames.
                    log.exception("gateway_inbound_dispatch_failed")
                    continue
                for frame in outbound:
                    await link.outbound.put(frame)
        finally:
            self._links.discard(link)
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender
            writer.close()

    async def _drain_outbound(self, link: _ClientLink) -> None:
        """Serialize and write every queued frame for one connection, in order.

        The sole writer of this connection's `StreamWriter`, so command replies
        and autonomous `push_deliver` frames never interleave a partial write. A
        transport failure (peer reset mid-write) ends the loop; `_handle_client`'s
        read side independently sees EOF and tears the connection down.
        """
        try:
            while True:
                frame = await link.outbound.get()
                link.writer.write(encode_frame(frame.to_json()))
                await link.writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            return

    async def push_deliver(self, directive: DeliveryDirective) -> None:
        """Proactively relay an autonomous fan-out to the Rust peer.

        Server-initiated broadcasts (world-clock `time_update`, weather
        narration) are not replies to any command, so they're enqueued directly
        as a standalone `Deliver` frame — never through a command's `deliveries`
        buffer or under `_directive_lock` (flush-now, not record-then-drain).

        Sent to exactly ONE active link: Rust resolves recipients from its own
        authoritative registry regardless of which link a frame arrives on, so
        pushing down every link would fan the same broadcast out N times. With no
        active links it is a harmless no-op — nobody is connected through the
        gateway to receive it.
        """
        link = next(iter(self._links), None)
        if link is None:
            return
        await link.outbound.put(Deliver(directive=directive))

    async def push_move(self, move: MovePlayer) -> None:
        """Proactively relay a room move to the Rust peer as a `MovePlayer` frame.

        The `POST /command` (HTMX) push path records the mover's room change on the
        :class:`GatewayPushManager` during command handling, then flushes it here —
        **before** its post-command room fan-out — so Rust's registry places the
        mover in the new room ahead of any later broadcast targeting it (gap-1).

        Like :meth:`push_deliver`, it is sent down exactly ONE active link (Rust owns
        the authoritative registry and applies the move regardless of which link it
        arrives on); with no active link it is a harmless no-op.
        """
        link = next(iter(self._links), None)
        if link is None:
            return
        await link.outbound.put(move)

    # -- dispatch (socket-free; unit-testable) ------------------------------

    async def handle_inbound(self, inbound: GatewayInbound) -> list[GatewayOutbound]:
        """Route one inbound frame to its handler, returning reply frames."""
        if isinstance(inbound, RedeemTicket):
            return [self._redeem_ticket(inbound)]
        if isinstance(inbound, ValidateAdminToken):
            return [self._validate_admin_token(inbound)]
        # Phase 4 execution round-trip (Option A). Both steps build their own local
        # directive-recording manager (in `build_look_request` / `apply_outcome`)
        # and never touch the adapter's shared `deliveries` buffer, so — unlike the
        # command/lifecycle handlers below — they need no directive lock: an
        # `ApplyOutcome`'s fan-out is returned inline in `OutcomeApplied`, not
        # drained from the shared buffer.
        if isinstance(inbound, BuildSnapshot):
            return [self._on_build_snapshot(inbound)]
        if isinstance(inbound, ApplyOutcome):
            return [await self._on_apply_outcome(inbound)]
        # Drain discipline (Phase 3b hardening): every handler below records into
        # — and then `drain()`s — the ONE shared `deliveries` buffer on the
        # manager, so each must run whole under the directive lock. Locking here,
        # at the dispatch level, guarantees a lifecycle event's record+drain and
        # a command's record+drain can never interleave and cross-contaminate
        # each other's directives (with concurrent client tasks in
        # `_handle_client`, an unlocked lifecycle drain could steal an in-flight
        # command's fan-out or vice versa). It also preserves today's implicit
        # at-most-one-outstanding-command serialization per connection.
        async with self._directive_lock:
            if isinstance(inbound, Connected):
                return await self._on_connected(inbound)
            if isinstance(inbound, Disconnected):
                return await self._on_disconnected(inbound)
            if isinstance(inbound, GatewayCommand):
                return await self._on_command(inbound)
        log.warning("gateway_inbound_unhandled: %s", type(inbound).__name__)
        return []

    # -- auth handoff (Python owns credential/session policy) ---------------

    def _redeem_ticket(self, msg: RedeemTicket) -> AuthResult:
        player_id = consume_ws_ticket(self._state, msg.ticket)
        return AuthResult(accepted=player_id is not None, player_id=player_id)

    def _validate_admin_token(self, msg: ValidateAdminToken) -> AdminAuthResult:
        # Admin validation replies with the shape-distinct `AdminAuthResult` (no
        # `player_id`): an admin token is not player-scoped, and Rust's
        # `auth::validate_admin_token` awaits `AdminAuthResult` on the control slot
        # to register the connection in its admin registry (Phase 3c cutover).
        try:
            decode_token(msg.token, self._state.settings.admin_jwt_secret)
        except jwt.InvalidTokenError:
            return AdminAuthResult(accepted=False)
        return AdminAuthResult(accepted=True)

    # -- connection lifecycle ----------------------------------------------

    async def _on_connected(self, msg: Connected) -> list[GatewayOutbound]:
        """Reproduce `main.websocket_endpoint`'s connect handshake, socket-free.

        Mints/resumes the session, builds the frames destined for the connecting
        client (`connected`, and `reconnect_sync` on a grace resume) as
        `ConnectAck.direct_frames`, and records the `player_joined` room broadcast
        as a `DeliveryDirective` relayed as a standalone `Deliver` — that frame is
        for *other* room occupants, not the connecting client, so it must not be
        folded into `direct_frames`.
        """
        state = self._state
        player_id = msg.player_id
        with (
            Session(state.game_engine) as game_session,
            Session(state.audit_engine) as audit_session,
        ):
            player = PlayerRepo(game_session).get(player_id)
            if player is None:
                # No connect-reject frame exists this phase; the socket-close path
                # is deferred to 3b's cutover. Log and ack nothing.
                log.warning("gateway_connected_unknown_player: %s", player_id)
                return []
            room_repo = RoomRepo(game_session)
            item_repo = ItemRepo(game_session)
            room = room_repo.get(player.current_room_id)
            if room is None:
                log.warning(
                    "gateway_connected_missing_room: %s", player.current_room_id
                )
                return []
            safety = SessionSafetyService(
                game_session=game_session,
                audit_session=audit_session,
                bus=state.bus,
                grace_seconds=state.settings.disconnect_grace_seconds,
            )
            safety.boot_active_session(player_id)
            session_result = safety.start_or_resume_session(player)
            session_id = session_result.player_session.id
            updates = player_ui_updates(player, room, room_repo, item_repo)
            connected_payload: JsonObject = {
                "type": "connected",
                "player_id": player_id,
                "room_id": room.id,
                "session_id": session_id,
                "reconnected": session_result.reconnected,
                "updates": updates,
            }
            reconnect_payload = (
                reconnect_sync_payload(player, session_id, updates)
                if session_result.reconnected
                else None
            )
            player_username = player.username
            room_id = room.id
            game_session.commit()
            audit_session.commit()

        state.admin_broadcaster.push(
            {
                "type": "player_connected",
                "player_id": player_id,
                "username": player_username,
                "room_id": room_id,
            }
        )
        self._manager.mark_connected(player_id, room_id, session_id)
        await self._manager.broadcast_to_room(
            room_id,
            {
                "type": "player_joined",
                "player_id": player_id,
                "username": player_username,
            },
            exclude=player_id,
        )
        direct_frames: list[JsonValue] = [connected_payload]
        if reconnect_payload is not None:
            direct_frames.append(reconnect_payload)
        ack = ConnectAck(
            session_id=session_id, room_id=room_id, direct_frames=direct_frames
        )
        deliveries = self._manager.drain()
        return [ack, *(Deliver(directive=d) for d in deliveries)]

    async def _on_disconnected(self, msg: Disconnected) -> list[GatewayOutbound]:
        """Reproduce the `WebSocketDisconnect` teardown, socket-free.

        `GracefulQuit` means the graceful-quit path already tore the session down
        (grace, player_left, follow-break) — skip, mirroring today's
        already-disconnected bail. `ClientClose` runs the involuntary-drop
        teardown: begin the grace period, narrate the connection flicker + a
        players-online refresh, then drop the mirror entry and broadcast
        `player_left`. Recorded broadcasts are relayed as `Deliver`s.

        The returned list **always ends with a terminal `DisconnectAck`**, even
        when there are no `Deliver`s (unknown player, or a `GracefulQuit` that
        already tore down). The Rust gateway sends `Disconnected` down the dying
        per-connection link and then *awaits* this `DisconnectAck` before dropping
        that link — so the leading `Deliver`s are guaranteed to have been read and
        dispatched to the remaining room siblings first. Without the ack, Rust
        would abort the link's read loop microseconds after writing `Disconnected`,
        and the still-connected players would silently miss the leave.
        """
        state = self._state
        player_id = msg.player_id
        # A disconnect means no `ApplyOutcome` will ever arrive for this player's
        # in-flight `BuildSnapshot`(s); reclaim their pending envelopes so they
        # can't leak (advisory: the `_pending` map's timeout/disconnect path).
        self._sweep_pending_for_player(player_id)
        if isinstance(msg.reason, ClientClose):
            session_id = self._manager.session_of(player_id)
            with (
                Session(state.game_engine) as game_session,
                Session(state.audit_engine) as audit_session,
            ):
                player = PlayerRepo(game_session).get(player_id)
                if player is not None and session_id is not None:
                    SessionSafetyService(
                        game_session=game_session,
                        audit_session=audit_session,
                        bus=state.bus,
                        grace_seconds=state.settings.disconnect_grace_seconds,
                    ).begin_grace_period(session_id, player)
                    game_session.commit()
                    audit_session.commit()
                    await self._manager.broadcast_to_room(
                        player.current_room_id,
                        {
                            "type": "feed_append",
                            "content": f"{player.username}'s connection flickers.",
                            "message_type": MessageType.ROOM_EVENT.value,
                        },
                        exclude=player.id,
                    )
                    await self._manager.broadcast_to_room(
                        player.current_room_id,
                        {
                            "type": "state_change",
                            "affected_panels": ["players-online"],
                            "actor_id": player.id,
                        },
                        exclude=player.id,
                    )
                    # Terminate any follow involving the dropped player and tell
                    # the still-connected other side (wired in 3b, mirroring the
                    # `/ws` WebSocketDisconnect handler: break_on_disconnect is
                    # now typed against ConnectionManagerProtocol, so the
                    # directive-recording manager passes structurally and the
                    # notices drain as `Deliver`s below).
                    follow_service = state.services.follow
                    if follow_service is not None:
                        await follow_service.break_on_disconnect(
                            self._manager, PlayerRepo(game_session), player_id
                        )
                    room_id = player.current_room_id
                    username = player.username
                else:
                    room_id = None
                    username = None
            if room_id is not None and username is not None:
                self._manager.mark_disconnected(player_id)
                await self._manager.broadcast_to_room(
                    room_id,
                    {
                        "type": "player_left",
                        "player_id": player_id,
                        "username": username,
                    },
                )
        else:  # GracefulQuit — already torn down by the graceful-quit path.
            self._manager.mark_disconnected(player_id)

        deliveries = self._manager.drain()
        # The terminal ack MUST be last so Rust only tears the link down once every
        # preceding teardown `Deliver` has been read and dispatched.
        return [*(Deliver(directive=d) for d in deliveries), DisconnectAck()]

    # -- command forwarding (shared pipeline) -------------------------------

    async def _on_command(self, msg: GatewayCommand) -> list[GatewayOutbound]:
        # Runs under `_directive_lock`, acquired by `handle_inbound` — the shared
        # directive buffer is exclusively this command's until the drain below.
        envelope = msg.envelope
        direct_reply = await handle_ws_command(
            self._state,
            self._manager,
            envelope.player_id,
            envelope.session_id,
            envelope.raw,
        )
        # Any mid-command room move must reach Rust's registry BEFORE the command's
        # own room-targeted deliveries are resolved — and before any later broadcast
        # to the mover's new room — so the `MovePlayer` frames precede the
        # `CommandReply`. Because the Rust read loop processes this link's frames in
        # order, ordering them first here is what guarantees a mover no longer misses
        # a subsequent broadcast to their new room (gap-1 fix).
        moves = self._manager.drain_moves()
        deliveries = self._manager.drain()
        reply = CommandReply(
            command_id=envelope.command_id,
            direct_reply=direct_reply,
            deliveries=deliveries,
        )
        return [*moves, reply]

    # -- Phase 4 execution round-trip (Rust owns execution; Python persists) --

    def _on_build_snapshot(self, msg: BuildSnapshot) -> GatewayOutbound:
        """Build the `ScriptRequest` snapshot Rust executes the routed verb against.

        Two short-circuits end the round-trip early with an `ExecutionRejected`
        frame (Phase 4b hardening) so the Rust driver never hangs and the frozen-
        session invariant is preserved:

        - **Frozen session (finding #2).** Checked FIRST, mirroring
          `handle_ws_command`'s guard: if the session's status is ``frozen``, reject
          *before* building the snapshot — no feature, no `ApplyOutcome`, no audit,
          no broadcast — returning the frozen ``system`` message for Rust to relay.
        - **Handler failure (finding #1).** Any exception in the frozen check or
          `build_look_request` (a vanished player/room, etc.) is caught, logged with
          traceback, and degraded to a client-facing in-game ``error`` reply rather
          than escaping to the silent dispatch catch-all (which would drop the reply
          and wedge the Rust `execute` driver awaiting `SnapshotReady`).

        On the success path the envelope is remembered keyed by its `command_id` so
        the correlated `ApplyOutcome` (which carries no envelope) can recover the
        persistence context. On either short-circuit the pending map is left
        untouched — there will be no `ApplyOutcome` for a rejected command. Only
        `look` is migrated this phase; other verbs are not yet routed here.

        The pending map is bounded: a Rust execute-timeout (or a dropped
        `ApplyOutcome`) would otherwise leak this entry forever, since Rust
        cancels on its side and sends Python nothing. The per-player sweep on
        `Disconnected` reclaims a disconnecting player's leaked entries; this hard
        cap (`_MAX_PENDING_OUTCOMES`) is the backstop for the pathological case,
        evicting the oldest entries first.
        """
        envelope = msg.envelope
        try:
            frozen_reply = self._frozen_reply(envelope)
            if frozen_reply is not None:
                return ExecutionRejected(
                    command_id=envelope.command_id, direct_reply=frozen_reply
                )
            request = build_look_request(self._state, envelope)
        except Exception:
            log.exception("gateway_build_snapshot_failed")
            return ExecutionRejected(
                command_id=envelope.command_id,
                direct_reply=_execution_error_reply(),
            )
        self._pending[envelope.command_id] = envelope
        self._evict_stale_pending()
        return SnapshotReady(command_id=envelope.command_id, request=request)

    def _evict_stale_pending(self) -> None:
        """Drop oldest pending envelopes once the map exceeds its hard cap.

        `dict` preserves insertion order, so the first keys are the oldest
        outstanding `BuildSnapshot`s — the ones a never-arriving `ApplyOutcome`
        would leak. Under the normal at-most-one-outstanding-command discipline
        this never trips; it only reclaims genuinely-leaked entries.
        """
        while len(self._pending) > _MAX_PENDING_OUTCOMES:
            stale_id = next(iter(self._pending))
            del self._pending[stale_id]
            log.warning("gateway_evicted_stale_pending_outcome: %s", stale_id)

    def _sweep_pending_for_player(self, player_id: str) -> None:
        """Reclaim any pending envelopes belonging to a disconnecting player.

        A disconnect means Rust will never send an `ApplyOutcome` for that
        player's in-flight `BuildSnapshot`(s), so their `_pending` entries would
        leak. Evict them here (called from the `Disconnected` teardown). Cheap:
        `_pending` is normally near-empty.
        """
        stale = [
            command_id
            for command_id, envelope in self._pending.items()
            if envelope.player_id == player_id
        ]
        for command_id in stale:
            del self._pending[command_id]
        if stale:
            log.debug(
                "gateway_swept_pending_outcomes player=%s count=%d",
                player_id,
                len(stale),
            )

    async def _on_apply_outcome(self, msg: ApplyOutcome) -> GatewayOutbound:
        """Persist the Rust-derived outcome and return the reply + deliveries.

        Recovers the originating envelope from the pending map (populated by the
        preceding `BuildSnapshot`), persists via `apply_outcome` — which commits
        both DBs *before* returning, preserving commit-before-publish — and packs
        the actor `direct_reply` and post-commit `deliveries` into `OutcomeApplied`
        for Rust to publish.

        Any failure (an unknown `command_id`, an unknown effect in `apply_outcome`,
        a vanished player/room) is caught, logged with traceback, and degraded to an
        `ExecutionRejected` frame carrying a client-facing in-game ``error`` reply
        (finding #1) — never allowed to escape to the silent dispatch catch-all,
        which would drop the reply and wedge the Rust driver awaiting
        `OutcomeApplied`. The pending entry is popped before persistence, so a
        failure here does not leak it.
        """
        try:
            envelope = self._pending.pop(msg.command_id, None)
            if envelope is None:
                raise ValidationError(
                    f"ApplyOutcome for unknown command_id: {msg.command_id!r}"
                )
            direct_reply, deliveries = await apply_outcome(
                self._state, envelope, msg.outcome
            )
        except Exception:
            log.exception("gateway_apply_outcome_failed")
            return ExecutionRejected(
                command_id=msg.command_id,
                direct_reply=_execution_error_reply(),
            )
        return OutcomeApplied(
            command_id=msg.command_id,
            direct_reply=direct_reply,
            deliveries=deliveries,
        )

    def _frozen_reply(self, envelope: CommandEnvelope) -> JsonObject | None:
        """Return the frozen-session reply if `envelope`'s session is frozen, else None.

        Reproduces `handle_ws_command`'s guard exactly
        (`player_repo.player_session(session_id).status == "frozen"`) against a
        read-only game session, so a frozen player's Rust-routed command is rejected
        with the byte-identical ``system`` message and executes/audits/broadcasts
        nothing.
        """
        with Session(self._state.game_engine) as game_session:
            session = PlayerRepo(game_session).player_session(envelope.session_id)
            is_frozen = session is not None and session.status == "frozen"
        if is_frozen:
            return {
                "type": "system",
                "text": FROZEN_SESSION_MESSAGE,
            }
        return None


class GatewayPushManager:
    """A `ConnectionManagerProtocol` that flushes *autonomous* broadcasts to Rust.

    Server-initiated broadcasts (the world-clock ``time_update`` and weather
    narration) are not triggered by any player command, so they bypass the
    command-path :class:`DirectiveConnectionManager`. In gateway mode they are
    routed here instead of to the real ``ConnectionManager`` — whose socket pool
    is empty, since clients connect to Rust — and each delivery method builds a
    :class:`DeliveryDirective` and pushes it to the adapter immediately as a
    standalone ``Deliver`` frame (flush-now, *not* record-then-drain). The
    ``target``/``exclude`` mapping is identical to
    :class:`DirectiveConnectionManager`'s so the wire payloads match byte-for-byte.

    Selection methods answer from the adapter's advisory connection mirror so a
    world-level broadcast still filters to rooms that actually have a gateway
    audience (e.g. weather narration's ``occupied_rooms`` gate).

    **Late-bound.** The autonomous handlers are registered on the bus *before*
    the adapter is constructed in the app lifespan, so the adapter is injected
    via :meth:`bind` afterwards. Before it is bound — and whenever no gateway
    client is connected — delivery is a harmless no-op and selection is empty
    (there is no audience yet).
    """

    def __init__(self) -> None:
        self._adapter: GatewayAdapter | None = None
        # Room moves recorded synchronously during command handling, flushed to Rust
        # as `MovePlayer` frames by `flush_moves` after the command (see below).
        self._pending_moves: list[MovePlayer] = []

    def bind(self, adapter: GatewayAdapter) -> None:
        """Attach the live adapter once the lifespan has constructed it."""
        self._adapter = adapter

    async def _push(self, directive: DeliveryDirective) -> None:
        if self._adapter is None:
            return
        await self._adapter.push_deliver(directive)

    async def flush_moves(self) -> None:
        """Forward every room move recorded since the last flush to Rust.

        The `POST /command` handler calls this **after** command execution and
        **before** its post-command fan-out (`broadcast_command_effects`), so Rust's
        registry learns the move ahead of any room-targeted broadcast that follows —
        the ordering guarantee the WS path gets for free by emitting `MovePlayer`
        frames before the `CommandReply`. Before the adapter is bound (or with no
        active gateway link) `push_move` is a harmless no-op.
        """
        pending = self._pending_moves
        self._pending_moves = []
        if self._adapter is None:
            return
        for move in pending:
            await self._adapter.push_move(move)

    # -- ConnectionManagerProtocol: delivery (pushes standalone Deliver frames) --

    async def send_to_player(self, player_id: str, message: JsonObject) -> None:
        await self._push(
            DeliveryDirective(
                target=PlayerTarget(id=player_id),
                exclude=None,
                payload=message,
                coalesce_key=coalesce_key_for(message),
            )
        )

    async def broadcast_to_room(
        self, room_id: str, message: JsonObject, exclude: str | None = None
    ) -> None:
        await self._push(
            DeliveryDirective(
                target=RoomTarget(id=room_id),
                exclude=exclude,
                payload=message,
                coalesce_key=coalesce_key_for(message),
            )
        )

    async def broadcast_global(
        self, message: JsonObject, exclude: str | None = None
    ) -> None:
        await self._push(
            DeliveryDirective(
                target=GlobalTarget(),
                exclude=exclude,
                payload=message,
                coalesce_key=coalesce_key_for(message),
            )
        )

    # -- ConnectionManagerProtocol: selection (reads the adapter's mirror) ------

    def move_player(self, player_id: str, from_room: str | None, to_room: str) -> None:
        # Update the advisory mirror without recording into the command-path
        # manager's own `moves` buffer (which this POST path never drains) — the move
        # is recorded here instead and flushed by `flush_moves` after the command.
        if self._adapter is not None:
            self._adapter.manager._apply_move_to_mirror(player_id, from_room, to_room)
        self._pending_moves.append(
            MovePlayer(player_id=player_id, from_room=from_room, to_room=to_room)
        )

    def players_in_room(self, room_id: str) -> list[str]:
        if self._adapter is None:
            return []
        return self._adapter.manager.players_in_room(room_id)

    def occupied_rooms(self) -> list[str]:
        if self._adapter is None:
            return []
        return self._adapter.manager.occupied_rooms()

    def connected_player_ids(self) -> list[str]:
        if self._adapter is None:
            return []
        return self._adapter.manager.connected_player_ids()

    def is_connected(self, player_id: str) -> bool:
        if self._adapter is None:
            return False
        return self._adapter.manager.is_connected(player_id)


class AdminGatewaySink:
    """Relays ``AdminBroadcaster`` events to Rust as ``Deliver(Admin)`` frames.

    In gateway mode admin consoles connect to Rust and live in Rust's admin
    registry, *not* this process's ``/admin/ws`` per-connection queue pool — so
    every event the :class:`~lorecraft.webui.admin.broadcaster.AdminBroadcaster`
    fans out must ALSO be relayed to Rust. This is registered as the broadcaster's
    synchronous sink (``AdminBroadcaster.set_gateway_sink``); each event is wrapped
    in a :class:`DeliveryDirective` targeting every admin console
    (:class:`~lorecraft.protocol.gateway.AdminTarget`) — with the Tier 2 coalescing
    key stamped by :func:`~lorecraft.gateway.coalescing.coalesce_key_for` — and
    pushed to Rust via :meth:`GatewayAdapter.push_deliver` down one active link.
    Rust fans it out to *all* admins from its registry regardless of which link it
    arrived on, exactly like an autonomous player broadcast.

    **Flag-off is untouched:** the sink is only registered when
    ``gateway_enabled``; with it unset the broadcaster's legacy per-connection
    ``asyncio.Queue`` path (drained by the Python ``/admin/ws`` handler) is
    byte-identical to before.

    **Late-bound** like :class:`GatewayPushManager`: the broadcaster (and its
    sink) is constructed before the adapter in the app lifespan, so :meth:`bind`
    injects the adapter afterward. Before binding — or with no active gateway
    link — forwarding is a harmless no-op.

    The broadcaster's ``push`` is *synchronous* (bus handlers call it from sync
    callbacks), while :meth:`GatewayAdapter.push_deliver` is async, so the relay is
    scheduled as a task on the running event loop, mirroring the autonomous
    clock-broadcast scheduling in ``main.py``. Called with no running loop (e.g. a
    unit test invoking ``push`` directly) it is a no-op.
    """

    def __init__(self) -> None:
        self._adapter: GatewayAdapter | None = None

    def bind(self, adapter: GatewayAdapter) -> None:
        """Attach the live adapter once the lifespan has constructed it."""
        self._adapter = adapter

    def directive_for(self, event: JsonObject) -> DeliveryDirective:
        """Build the ``Deliver(Admin)`` directive for one admin event (pure)."""
        return DeliveryDirective(
            target=AdminTarget(),
            exclude=None,
            payload=event,
            coalesce_key=coalesce_key_for(event),
        )

    def __call__(self, event: JsonObject) -> None:
        adapter = self._adapter
        if adapter is None:
            return
        directive = self.directive_for(event)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no running loop (e.g. tests) — nothing to schedule onto
        loop.create_task(adapter.push_deliver(directive))
