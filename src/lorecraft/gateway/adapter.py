"""Python gateway adapter — the UDS listener for the Rust-port gateway (Phase 3).

Runs an `asyncio` Unix-domain-socket server speaking length-prefixed JSON
(4-byte big-endian length + UTF-8 JSON). The Rust gateway owns client sockets and
forwards framed `GatewayInbound` messages; this adapter dispatches them to the
*existing* Python credential/session/command logic and replies with framed
`GatewayOutbound` messages:

- `RedeemTicket`  -> `consume_ws_ticket`        -> `AuthResult`
- `ValidateAdminToken` -> admin `decode_token`  -> `AuthResult`
- `Connected`     -> session boot/resume        -> `ConnectAck` (+ `Deliver`s)
- `Disconnected`  -> grace/flicker/player_left teardown -> `Deliver`s
- `Command`       -> shared `handle_ws_command`  -> `CommandReply`

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

from lorecraft.gateway.connection_manager import DirectiveConnectionManager
from lorecraft.protocol.gateway import (
    AuthResult,
    ClientClose,
    Connected,
    ConnectAck,
    CommandReply,
    Deliver,
    DeliveryDirective,
    Disconnected,
    GatewayCommand,
    GatewayInbound,
    GatewayOutbound,
    GlobalTarget,
    PlayerTarget,
    RedeemTicket,
    RoomTarget,
    ValidateAdminToken,
    gateway_inbound_from_json,
)
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.save import SessionSafetyService
from lorecraft.state import AppState
from lorecraft.types import JsonObject, JsonValue
from lorecraft.webui.admin.auth import decode_token
from lorecraft.webui.player.auth import consume_ws_ticket
from lorecraft.webui.player.ui_snapshots import (
    player_ui_updates,
    reconnect_sync_payload,
)
from lorecraft.webui.player.ws_command import handle_ws_command

log = logging.getLogger(__name__)

_LENGTH_PREFIX_BYTES = 4


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

    # -- dispatch (socket-free; unit-testable) ------------------------------

    async def handle_inbound(self, inbound: GatewayInbound) -> list[GatewayOutbound]:
        """Route one inbound frame to its handler, returning reply frames."""
        if isinstance(inbound, RedeemTicket):
            return [self._redeem_ticket(inbound)]
        if isinstance(inbound, ValidateAdminToken):
            return [self._validate_admin_token(inbound)]
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
                return [await self._on_command(inbound)]
        log.warning("gateway_inbound_unhandled: %s", type(inbound).__name__)
        return []

    # -- auth handoff (Python owns credential/session policy) ---------------

    def _redeem_ticket(self, msg: RedeemTicket) -> AuthResult:
        player_id = consume_ws_ticket(self._state, msg.ticket)
        return AuthResult(accepted=player_id is not None, player_id=player_id)

    def _validate_admin_token(self, msg: ValidateAdminToken) -> AuthResult:
        try:
            decode_token(msg.token, self._state.settings.admin_jwt_secret)
        except jwt.InvalidTokenError:
            return AuthResult(accepted=False, player_id=None)
        # Admin tokens carry no player_id. `AuthResult.player_id` is reused loosely
        # between the player and admin auth paths here; the admin channel doesn't
        # need a player_id, so None-on-success is acceptable for now. Revisit when
        # sub-slice 3c wires the real admin `/admin/ws` cutover.
        return AuthResult(accepted=True, player_id=None)

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
        """
        state = self._state
        player_id = msg.player_id
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
        return [Deliver(directive=d) for d in deliveries]

    # -- command forwarding (shared pipeline) -------------------------------

    async def _on_command(self, msg: GatewayCommand) -> CommandReply:
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
        deliveries = self._manager.drain()
        return CommandReply(
            command_id=envelope.command_id,
            direct_reply=direct_reply,
            deliveries=deliveries,
        )


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

    def bind(self, adapter: GatewayAdapter) -> None:
        """Attach the live adapter once the lifespan has constructed it."""
        self._adapter = adapter

    async def _push(self, directive: DeliveryDirective) -> None:
        if self._adapter is None:
            return
        await self._adapter.push_deliver(directive)

    # -- ConnectionManagerProtocol: delivery (pushes standalone Deliver frames) --

    async def send_to_player(self, player_id: str, message: JsonObject) -> None:
        await self._push(
            DeliveryDirective(
                target=PlayerTarget(id=player_id), exclude=None, payload=message
            )
        )

    async def broadcast_to_room(
        self, room_id: str, message: JsonObject, exclude: str | None = None
    ) -> None:
        await self._push(
            DeliveryDirective(
                target=RoomTarget(id=room_id), exclude=exclude, payload=message
            )
        )

    async def broadcast_global(
        self, message: JsonObject, exclude: str | None = None
    ) -> None:
        await self._push(
            DeliveryDirective(target=GlobalTarget(), exclude=exclude, payload=message)
        )

    # -- ConnectionManagerProtocol: selection (reads the adapter's mirror) ------

    def move_player(self, player_id: str, from_room: str | None, to_room: str) -> None:
        if self._adapter is not None:
            self._adapter.manager.move_player(player_id, from_room, to_room)

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
