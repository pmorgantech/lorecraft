"""Gateway framing protocol — Python mirror of the Rust `gateway.rs` module.

These are the Rust↔Python transport envelopes for Phase 3 (migrate transport and
connection ownership). The Rust gateway owns client sockets; this Python side runs
a UDS listener (the "gateway adapter"). ``GatewayInbound`` (Rust→Python) and
``GatewayOutbound`` (Python→Rust) are the frames exchanged over that channel.

Like ``effects.py`` / ``messages.py``, each tagged-enum variant is a frozen
dataclass sharing a base class; ``to_json``/``from_json`` reproduce the exact
``{"type": ..., ...fields}`` internally-tagged wire shape serde emits, so a value
can be JSON-diffed against the Rust side.

This module is **additive** — ``CommandEnvelope`` and every existing protocol type
are reused verbatim. A forwarded command is the ``GatewayCommand`` variant wrapping
an unmodified envelope (flattened alongside the tag, mirroring the Rust newtype
variant ``GatewayInbound::Command``).

Resolved design decisions (Phase 3 kickoff spec, 2026-07-13), documented on the
Rust side too:

- **OPEN ITEM 1 — request/reply correlation.** ``CommandReply`` carries a
  ``command_id`` correlating it back to the originating command over the multiplexed
  UDS stream; ``Deliver`` (unsolicited async pushes — clock ticks, weather,
  cross-player deliveries) carries no correlation id.
- **``DeliveryDirective.payload`` is an opaque relay.** Neither side interprets it;
  it preserves the legacy WebSocket frame shapes byte-exactly.
- **Room ids are plain ``str``.** There is no ``RoomId`` newtype, matching the Rust
  ``DeliveryTarget::Room`` / ``ConnectAck`` shapes.

Resolved admin-push design (Phase 3c, 2026-07-13), documented on the Rust side too:

- **Admin fan-out reuses ``Deliver``.** ``AdminTarget`` (``{"type": "Admin"}``) names
  "every connected admin console"; ``AdminBroadcaster.push`` sends an admin event as
  a normal ``Deliver(DeliveryDirective(target=AdminTarget(), ...))`` frame and Rust
  fans it out to admins from its admin registry — no separate admin-deliver frame.
- **Admin auth is the shape-distinct ``AdminAuthResult``.** A validated admin carries
  no ``player_id`` (admin tokens are not player-scoped), so admin validation replies
  with ``AdminAuthResult(accepted)`` rather than overloading the player ``AuthResult``.
- **Admin lifecycle is Rust-local — no protocol frame.** Admin connections are
  stateless and push-only (no ``SessionSafetyService`` grace like players); Rust owns
  the admin registry (register after an accepted ``AdminAuthResult``, deregister on
  socket close) and Python is never told about admin connect/disconnect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Self

from lorecraft.errors import ValidationError
from lorecraft.protocol._coerce import (
    optional_str,
    require_bool,
    require_dict,
    require_list,
    require_object,
    require_str,
)
from lorecraft.protocol.envelope import CommandEnvelope, CommandId, PlayerId, SessionId
from lorecraft.types import JsonObject, JsonValue

# --- DisconnectReason ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DisconnectReason:
    """Base class for the two connection-teardown reasons.

    Internally tagged like the Rust enum (``{"type": "ClientClose"}``) rather than a
    bare string, so it stays extensible.
    """

    TAG: ClassVar[str] = ""

    def to_json(self) -> JsonObject:
        return {"type": self.TAG}


@dataclass(frozen=True, slots=True)
class ClientClose(DisconnectReason):
    """The client socket closed (an involuntary drop); Python begins disconnect grace."""

    TAG: ClassVar[str] = "ClientClose"


@dataclass(frozen=True, slots=True)
class GracefulQuit(DisconnectReason):
    """The player deliberately quit; Python skips the double-teardown path."""

    TAG: ClassVar[str] = "GracefulQuit"


_DISCONNECT_REASONS: dict[str, type[DisconnectReason]] = {
    cls.TAG: cls for cls in (ClientClose, GracefulQuit)
}


def disconnect_reason_from_json(data: JsonObject) -> DisconnectReason:
    """Reconstruct a ``DisconnectReason`` from its tagged-JSON shape."""
    tag = data.get("type")
    if not isinstance(tag, str) or tag not in _DISCONNECT_REASONS:
        raise ValidationError(f"unknown disconnect reason: {tag!r}")
    return _DISCONNECT_REASONS[tag]()


# --- DeliveryTarget --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeliveryTarget:
    """Base class for the fan-out recipient-set variants."""

    TAG: ClassVar[str] = ""

    def to_json(self) -> JsonObject:
        return {"type": self.TAG}


@dataclass(frozen=True, slots=True)
class PlayerTarget(DeliveryTarget):
    """Deliver to a single player (``{"type": "Player", "id": ...}``)."""

    TAG: ClassVar[str] = "Player"
    id: PlayerId

    def to_json(self) -> JsonObject:
        return {"type": self.TAG, "id": self.id}


@dataclass(frozen=True, slots=True)
class RoomTarget(DeliveryTarget):
    """Deliver to everyone in a room (plain room id; no ``RoomId`` newtype)."""

    TAG: ClassVar[str] = "Room"
    id: str

    def to_json(self) -> JsonObject:
        return {"type": self.TAG, "id": self.id}


@dataclass(frozen=True, slots=True)
class GlobalTarget(DeliveryTarget):
    """Deliver to every connected player (``{"type": "Global"}``)."""

    TAG: ClassVar[str] = "Global"


@dataclass(frozen=True, slots=True)
class AdminTarget(DeliveryTarget):
    """Deliver to every connected admin console (``{"type": "Admin"}``).

    Resolved against Rust's admin registry rather than the player registry (see the
    resolved admin-push design in ``gateway.rs``); the opaque ``payload`` is relayed
    unchanged, exactly like ``RoomTarget``/``GlobalTarget`` for players. This lets
    ``AdminBroadcaster.push`` fan an admin event out as an ordinary
    ``Deliver`` frame.
    """

    TAG: ClassVar[str] = "Admin"


def delivery_target_from_json(data: JsonObject) -> DeliveryTarget:
    """Reconstruct a ``DeliveryTarget`` variant from its tagged-JSON shape."""
    tag = data.get("type")
    if tag == PlayerTarget.TAG:
        return PlayerTarget(id=require_str(data, "id"))
    if tag == RoomTarget.TAG:
        return RoomTarget(id=require_str(data, "id"))
    if tag == GlobalTarget.TAG:
        return GlobalTarget()
    if tag == AdminTarget.TAG:
        return AdminTarget()
    raise ValidationError(f"unknown delivery target: {tag!r}")


# --- DeliveryDirective -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeliveryDirective:
    """A single fan-out directive: relay an opaque ``payload`` to a recipient set.

    Rust resolves ``target``/``exclude`` against its authoritative connection map and
    relays ``payload`` without interpreting it.

    ``coalesce_key`` is the optional Phase 3c coalescing key (design decision 10).
    Python is the **policy owner**: it stamps a stable per-panel key on idempotent
    ``state_change``/panel-refresh directives so Rust's outbound-queue *mechanism* can
    keep-latest without interpreting the opaque ``payload``, and leaves it ``None`` for
    ``feed_append`` (every one matters). It is additive and defaults to ``None``: to
    keep every pre-existing frame's wire shape byte-identical it is **omitted** from
    ``to_json`` when unset, mirroring the Rust ``skip_serializing_if = "Option::is_none"``.
    This task only plumbs the field; the actual per-directive stamping is a later task.
    """

    target: DeliveryTarget
    exclude: PlayerId | None
    payload: JsonValue
    coalesce_key: str | None = None

    def to_json(self) -> JsonObject:
        out: JsonObject = {
            "target": self.target.to_json(),
            "exclude": self.exclude,
            "payload": self.payload,
        }
        if self.coalesce_key is not None:
            out["coalesce_key"] = self.coalesce_key
        return out

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        return cls(
            target=delivery_target_from_json(require_dict(data, "target")),
            exclude=optional_str(data, "exclude"),
            payload=data.get("payload"),
            coalesce_key=optional_str(data, "coalesce_key"),
        )


# --- GatewayInbound (Rust -> Python) ---------------------------------------


@dataclass(frozen=True, slots=True)
class GatewayInbound:
    """Base class for frames sent from the Rust gateway to the Python adapter."""

    TAG: ClassVar[str] = ""

    def to_json(self) -> JsonObject:
        raise NotImplementedError  # pragma: no cover - abstract base


@dataclass(frozen=True, slots=True)
class RedeemTicket(GatewayInbound):
    """Ask Python to redeem a single-use player WebSocket ticket."""

    TAG: ClassVar[str] = "RedeemTicket"
    ticket: str

    def to_json(self) -> JsonObject:
        return {"type": self.TAG, "ticket": self.ticket}


@dataclass(frozen=True, slots=True)
class ValidateAdminToken(GatewayInbound):
    """Ask Python to validate an admin JWT (``?token=``) for the admin channel."""

    TAG: ClassVar[str] = "ValidateAdminToken"
    token: str

    def to_json(self) -> JsonObject:
        return {"type": self.TAG, "token": self.token}


@dataclass(frozen=True, slots=True)
class Connected(GatewayInbound):
    """A player's connection has been established; Python mints/resumes a session."""

    TAG: ClassVar[str] = "Connected"
    player_id: PlayerId

    def to_json(self) -> JsonObject:
        return {"type": self.TAG, "player_id": self.player_id}


@dataclass(frozen=True, slots=True)
class Disconnected(GatewayInbound):
    """A player's connection has ended."""

    TAG: ClassVar[str] = "Disconnected"
    player_id: PlayerId
    reason: DisconnectReason

    def to_json(self) -> JsonObject:
        return {
            "type": self.TAG,
            "player_id": self.player_id,
            "reason": self.reason.to_json(),
        }


@dataclass(frozen=True, slots=True)
class GatewayCommand(GatewayInbound):
    """A forwarded command to execute. Wraps an unmodified ``CommandEnvelope``;
    serializes as ``{"type": "Command", ...envelope fields}`` (the Rust newtype
    variant ``GatewayInbound::Command``)."""

    TAG: ClassVar[str] = "Command"
    envelope: CommandEnvelope

    def to_json(self) -> JsonObject:
        return {"type": self.TAG, **self.envelope.to_json()}


def gateway_inbound_from_json(data: JsonObject) -> GatewayInbound:
    """Reconstruct a ``GatewayInbound`` variant from its tagged-JSON shape."""
    tag = data.get("type")
    if tag == RedeemTicket.TAG:
        return RedeemTicket(ticket=require_str(data, "ticket"))
    if tag == ValidateAdminToken.TAG:
        return ValidateAdminToken(token=require_str(data, "token"))
    if tag == Connected.TAG:
        return Connected(player_id=require_str(data, "player_id"))
    if tag == Disconnected.TAG:
        return Disconnected(
            player_id=require_str(data, "player_id"),
            reason=disconnect_reason_from_json(require_dict(data, "reason")),
        )
    if tag == GatewayCommand.TAG:
        # The envelope is flattened alongside the tag; `from_json` ignores "type".
        return GatewayCommand(envelope=CommandEnvelope.from_json(data))
    raise ValidationError(f"unknown gateway inbound type: {tag!r}")


# --- GatewayOutbound (Python -> Rust) --------------------------------------


@dataclass(frozen=True, slots=True)
class GatewayOutbound:
    """Base class for frames sent from the Python adapter back to the Rust gateway."""

    TAG: ClassVar[str] = ""

    def to_json(self) -> JsonObject:
        raise NotImplementedError  # pragma: no cover - abstract base


@dataclass(frozen=True, slots=True)
class AuthResult(GatewayOutbound):
    """The result of a player ``RedeemTicket`` handoff. On rejection, ``accepted`` is
    ``False`` and ``player_id`` is ``None``; Rust closes with 1008. Admin-token
    validation uses the shape-distinct ``AdminAuthResult`` instead (see the resolved
    admin-push design in ``gateway.rs``)."""

    TAG: ClassVar[str] = "AuthResult"
    accepted: bool
    player_id: PlayerId | None

    def to_json(self) -> JsonObject:
        return {
            "type": self.TAG,
            "accepted": self.accepted,
            "player_id": self.player_id,
        }


@dataclass(frozen=True, slots=True)
class AdminAuthResult(GatewayOutbound):
    """The result of a ``ValidateAdminToken`` handoff for the push-only admin
    console. Deliberately **distinct** from ``AuthResult`` and carrying no
    ``player_id`` — an admin token is not player-scoped, so a validated admin cannot
    be routed through the player session path. On rejection ``accepted`` is ``False``
    and Rust closes with 1008."""

    TAG: ClassVar[str] = "AdminAuthResult"
    accepted: bool

    def to_json(self) -> JsonObject:
        return {"type": self.TAG, "accepted": self.accepted}


@dataclass(frozen=True, slots=True)
class ConnectAck(GatewayOutbound):
    """Acknowledges a ``Connected`` handshake with the minted/resumed session and the
    frames to replay into the just-connected client."""

    TAG: ClassVar[str] = "ConnectAck"
    session_id: SessionId
    room_id: str
    direct_frames: list[JsonValue] = field(default_factory=list)

    def to_json(self) -> JsonObject:
        return {
            "type": self.TAG,
            "session_id": self.session_id,
            "room_id": self.room_id,
            "direct_frames": list(self.direct_frames),
        }


@dataclass(frozen=True, slots=True)
class CommandReply(GatewayOutbound):
    """The synchronous reply to a forwarded command, correlated by ``command_id``
    (OPEN ITEM 1 resolution)."""

    TAG: ClassVar[str] = "CommandReply"
    command_id: CommandId
    direct_reply: JsonValue
    deliveries: list[DeliveryDirective] = field(default_factory=list)

    def to_json(self) -> JsonObject:
        return {
            "type": self.TAG,
            "command_id": self.command_id,
            "direct_reply": self.direct_reply,
            "deliveries": [d.to_json() for d in self.deliveries],
        }


@dataclass(frozen=True, slots=True)
class Deliver(GatewayOutbound):
    """An unsolicited async push. Carries no correlation id (not a reply)."""

    TAG: ClassVar[str] = "Deliver"
    directive: DeliveryDirective

    def to_json(self) -> JsonObject:
        return {"type": self.TAG, "directive": self.directive.to_json()}


@dataclass(frozen=True, slots=True)
class MovePlayer(GatewayOutbound):
    """A registry state update: a player changed rooms during command handling.

    **Not a delivery** — it carries no payload and fans nothing out. It exists solely
    to keep Rust's authoritative ``player -> room`` / ``room -> players`` maps in step
    with Python's mid-command ``move_player``, so a subsequent ``RoomTarget`` broadcast
    aimed at the mover's **new** room actually reaches them. Rust applies it by calling
    ``ConnectionRegistry::move_player``.

    Emitted **in order ahead of** the moving command's own deliveries down the same
    link: the WS ``CommandReply`` path returns the move frames just before the reply,
    and the HTMX ``POST /command`` push path flushes them just before its post-command
    fan-out. ``from_room`` is ``None`` when the origin is unknown (mirrors the Rust
    ``Option<String>``); the registry treats an absent/empty origin as "unset"."""

    TAG: ClassVar[str] = "MovePlayer"
    player_id: PlayerId
    from_room: str | None
    to_room: str

    def to_json(self) -> JsonObject:
        return {
            "type": self.TAG,
            "player_id": self.player_id,
            "from_room": self.from_room,
            "to_room": self.to_room,
        }


@dataclass(frozen=True, slots=True)
class DisconnectAck(GatewayOutbound):
    """Terminal ack that a ``Disconnected`` teardown finished (no fields).

    Emitted **after** the teardown's fan-out ``Deliver``s (``player_left``, the
    connection-flicker narration, the ``players-online`` refresh, follow-break
    notices), so the Rust gateway can await it and only drop the dying
    per-connection link once those ``Deliver``s have been read and dispatched to
    the remaining room siblings. Mirrors the Rust ``GatewayOutbound::DisconnectAck``
    bare-tag variant."""

    TAG: ClassVar[str] = "DisconnectAck"

    def to_json(self) -> JsonObject:
        return {"type": self.TAG}


def gateway_outbound_from_json(data: JsonObject) -> GatewayOutbound:
    """Reconstruct a ``GatewayOutbound`` variant from its tagged-JSON shape."""
    tag = data.get("type")
    if tag == AuthResult.TAG:
        return AuthResult(
            accepted=require_bool(data, "accepted"),
            player_id=optional_str(data, "player_id"),
        )
    if tag == AdminAuthResult.TAG:
        return AdminAuthResult(accepted=require_bool(data, "accepted"))
    if tag == ConnectAck.TAG:
        return ConnectAck(
            session_id=require_str(data, "session_id"),
            room_id=require_str(data, "room_id"),
            direct_frames=list(require_list(data, "direct_frames")),
        )
    if tag == CommandReply.TAG:
        return CommandReply(
            command_id=require_str(data, "command_id"),
            direct_reply=data.get("direct_reply"),
            deliveries=[
                DeliveryDirective.from_json(require_object(item))
                for item in require_list(data, "deliveries")
            ],
        )
    if tag == Deliver.TAG:
        return Deliver(
            directive=DeliveryDirective.from_json(require_dict(data, "directive"))
        )
    if tag == MovePlayer.TAG:
        return MovePlayer(
            player_id=require_str(data, "player_id"),
            from_room=optional_str(data, "from_room"),
            to_room=require_str(data, "to_room"),
        )
    if tag == DisconnectAck.TAG:
        return DisconnectAck()
    raise ValidationError(f"unknown gateway outbound type: {tag!r}")
