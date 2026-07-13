"""Language-neutral protocol contracts (Tier 1 mechanism).

Field-for-field Python mirror of the Rust `lorecraft-protocol` crate: the value
types exchanged between engine, persistence, and scripting layers. Frozen
dataclasses (matching `session_replay.py`, no new dependency) with a wire shape
identical to the Rust serde output, so a value can be JSON-diffed across languages.

No feature-specific fields live here — `EntitySnapshot.attributes` is opaque
precisely so no feature's opinion (Tier 2 policy) leaks into the mechanism layer.
"""

from __future__ import annotations

from lorecraft.protocol.effects import (
    AdjustMeter,
    Effect,
    EmitEvent,
    MoveEntity,
    SendNarration,
    SetFlag,
    TransferItem,
    effect_from_json,
)
from lorecraft.protocol.envelope import (
    ActorId,
    CommandEnvelope,
    CommandId,
    CommandOutcome,
    Diagnostic,
    OutcomeStatus,
    PlayerId,
    SessionId,
    WorldId,
)
from lorecraft.protocol.gateway import (
    AuthResult,
    ClientClose,
    Connected,
    ConnectAck,
    CommandReply,
    Deliver,
    DeliveryDirective,
    DeliveryTarget,
    Disconnected,
    DisconnectReason,
    GatewayCommand,
    GatewayInbound,
    GatewayOutbound,
    GlobalTarget,
    GracefulQuit,
    PlayerTarget,
    RedeemTicket,
    RoomTarget,
    ValidateAdminToken,
    delivery_target_from_json,
    disconnect_reason_from_json,
    gateway_inbound_from_json,
    gateway_outbound_from_json,
)
from lorecraft.protocol.messages import (
    Feed,
    OutboundMessage,
    PanelUpdate,
    message_from_json,
)
from lorecraft.protocol.script import (
    EmittedEvent,
    ScheduledWork,
    ScriptBudget,
    ScriptRequest,
    ScriptResult,
)
from lorecraft.protocol.snapshot import EntitySnapshot
from lorecraft.protocol.version import PROTOCOL_VERSION

__all__ = [
    "PROTOCOL_VERSION",
    # ids
    "WorldId",
    "ActorId",
    "PlayerId",
    "SessionId",
    "CommandId",
    # envelope
    "CommandEnvelope",
    "CommandOutcome",
    "OutcomeStatus",
    "Diagnostic",
    # snapshot
    "EntitySnapshot",
    # effects
    "Effect",
    "MoveEntity",
    "TransferItem",
    "AdjustMeter",
    "SetFlag",
    "EmitEvent",
    "SendNarration",
    "effect_from_json",
    # messages
    "OutboundMessage",
    "Feed",
    "PanelUpdate",
    "message_from_json",
    # gateway framing (Rust-port Phase 3)
    "GatewayInbound",
    "RedeemTicket",
    "ValidateAdminToken",
    "Connected",
    "Disconnected",
    "GatewayCommand",
    "gateway_inbound_from_json",
    "GatewayOutbound",
    "AuthResult",
    "ConnectAck",
    "CommandReply",
    "Deliver",
    "gateway_outbound_from_json",
    "DisconnectReason",
    "ClientClose",
    "GracefulQuit",
    "disconnect_reason_from_json",
    "DeliveryDirective",
    "DeliveryTarget",
    "PlayerTarget",
    "RoomTarget",
    "GlobalTarget",
    "delivery_target_from_json",
    # script
    "ScriptBudget",
    "EmittedEvent",
    "ScheduledWork",
    "ScriptRequest",
    "ScriptResult",
]
