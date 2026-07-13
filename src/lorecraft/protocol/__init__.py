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
    # script
    "ScriptBudget",
    "EmittedEvent",
    "ScheduledWork",
    "ScriptRequest",
    "ScriptResult",
]
