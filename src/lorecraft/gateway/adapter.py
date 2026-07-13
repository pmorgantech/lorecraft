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

Not wired into the app factory this phase — a later cutover task starts it.
Composition/web-host layer: imports engine + features + web hosts, never
imported *by* `engine/`.
"""

from __future__ import annotations

import asyncio
import json
import logging

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
    Disconnected,
    GatewayCommand,
    GatewayInbound,
    GatewayOutbound,
    RedeemTicket,
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
        # Commands from a connection are handled at-most-one-outstanding (matching
        # today's implicit per-socket serialization); the lock keeps the shared
        # directive buffer isolated per command even across multiplexed frames.
        self._command_lock = asyncio.Lock()
        self._server: asyncio.AbstractServer | None = None

    @property
    def manager(self) -> DirectiveConnectionManager:
        return self._manager

    # -- server lifecycle ---------------------------------------------------

    async def start(self) -> asyncio.AbstractServer:
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=self._socket_path
        )
        log.info("gateway adapter listening on %s", self._socket_path)
        return self._server

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
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
                    writer.write(encode_frame(frame.to_json()))
                await writer.drain()
        finally:
            writer.close()

    # -- dispatch (socket-free; unit-testable) ------------------------------

    async def handle_inbound(self, inbound: GatewayInbound) -> list[GatewayOutbound]:
        """Route one inbound frame to its handler, returning reply frames."""
        if isinstance(inbound, RedeemTicket):
            return [self._redeem_ticket(inbound)]
        if isinstance(inbound, ValidateAdminToken):
            return [self._validate_admin_token(inbound)]
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
                    room_id = player.current_room_id
                    username = player.username
                else:
                    room_id = None
                    username = None
            # follow-break is deferred: FollowService.break_on_disconnect is typed
            # against the concrete ConnectionManager (and needs `is_connected` on a
            # 2-method surface); wiring it through the injectable manager belongs to
            # sub-slice 3b's live lifecycle cutover, not this foundation slice.
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
        envelope = msg.envelope
        async with self._command_lock:
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
