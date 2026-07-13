"""Command ingress envelope and outcome — Python mirror of `envelope.rs`.

ID fields are plain `str` aliases (matching the Rust `#[serde(transparent)]`
newtypes' bare-string JSON), so no wrapping is needed on this side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Self

from lorecraft.errors import ValidationError
from lorecraft.protocol._coerce import (
    optional_int,
    optional_str_list,
    require_int,
    require_list,
    require_object,
    require_str,
)
from lorecraft.protocol.effects import Effect, effect_from_json
from lorecraft.protocol.messages import OutboundMessage, message_from_json
from lorecraft.types import JsonObject

# ID aliases — bare strings on the wire, matching Rust's transparent newtypes.
WorldId = str
ActorId = str
PlayerId = str
SessionId = str
CommandId = str


class OutcomeStatus(str, Enum):
    """Terminal status of a command's execution.

    Subclasses ``str`` so a value serializes as its plain variant name (matching
    the Rust externally-tagged unit-enum wire shape, e.g. ``"Executed"``).
    """

    EXECUTED = "Executed"
    BLOCKED = "Blocked"
    FAILED = "Failed"
    TIMED_OUT = "TimedOut"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A diagnostic annotation attached to an outcome or script result."""

    level: str
    message: str

    def to_json(self) -> JsonObject:
        return {"level": self.level, "message": self.message}

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        return cls(
            level=require_str(data, "level"), message=require_str(data, "message")
        )


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    """A command as admitted to the engine, with routing/idempotency metadata."""

    protocol_version: int
    world_id: WorldId
    actor_id: ActorId
    player_id: PlayerId
    session_id: SessionId
    command_id: CommandId
    receive_sequence: int
    deadline_ms: int
    raw: str

    def to_json(self) -> JsonObject:
        return {
            "protocol_version": self.protocol_version,
            "world_id": self.world_id,
            "actor_id": self.actor_id,
            "player_id": self.player_id,
            "session_id": self.session_id,
            "command_id": self.command_id,
            "receive_sequence": self.receive_sequence,
            "deadline_ms": self.deadline_ms,
            "raw": self.raw,
        }

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        return cls(
            protocol_version=require_int(data, "protocol_version"),
            world_id=require_str(data, "world_id"),
            actor_id=require_str(data, "actor_id"),
            player_id=require_str(data, "player_id"),
            session_id=require_str(data, "session_id"),
            command_id=require_str(data, "command_id"),
            receive_sequence=require_int(data, "receive_sequence"),
            deadline_ms=require_int(data, "deadline_ms"),
            raw=require_str(data, "raw"),
        )


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """The authoritative result of executing a ``CommandEnvelope``."""

    command_id: CommandId
    status: OutcomeStatus
    commit_sequence: int | None = None
    messages: list[OutboundMessage] = field(default_factory=list)
    applied_effects: list[Effect] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    # Narration routed to the actor's ORIGIN room (the room they were in when the
    # command ran), excluding the actor — the engine's ``ctx.room_messages``
    # (``ctx.tell_room``). Empty for verbs that produce none (e.g. ``look``). The
    # movement effect-applier appends these onto ``ctx.room_messages`` before
    # ``broadcast_command_effects`` routes them to the origin room.
    room_narration: list[str] = field(default_factory=list)
    # Narration routed to the actor's DESTINATION room (the post-command room),
    # excluding the actor — the engine's ``ctx.arrival_messages``
    # (``ctx.tell_arrival``). Empty for verbs that do not move the actor.
    arrival_narration: list[str] = field(default_factory=list)

    def to_json(self) -> JsonObject:
        # Nested effects/messages carry their own ``{"type": ...}`` discriminator;
        # recurse through their ``to_json`` rather than flattening with asdict.
        out: JsonObject = {
            "command_id": self.command_id,
            "status": self.status.value,
            "commit_sequence": self.commit_sequence,
            "messages": [message.to_json() for message in self.messages],
            "applied_effects": [effect.to_json() for effect in self.applied_effects],
            "diagnostics": [diagnostic.to_json() for diagnostic in self.diagnostics],
        }
        # Additive + defaulted to empty: mirror the Rust
        # ``skip_serializing_if = "Vec::is_empty"`` so a read-only outcome's wire
        # shape (e.g. ``look``) stays byte-identical to before the fields existed.
        if self.room_narration:
            out["room_narration"] = list(self.room_narration)
        if self.arrival_narration:
            out["arrival_narration"] = list(self.arrival_narration)
        return out

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        status_value = require_str(data, "status")
        try:
            status = OutcomeStatus(status_value)
        except ValueError as exc:
            raise ValidationError(f"unknown outcome status: {status_value!r}") from exc
        return cls(
            command_id=require_str(data, "command_id"),
            status=status,
            commit_sequence=optional_int(data, "commit_sequence"),
            messages=[
                message_from_json(require_object(item))
                for item in require_list(data, "messages")
            ],
            applied_effects=[
                effect_from_json(require_object(item))
                for item in require_list(data, "applied_effects")
            ],
            diagnostics=[
                Diagnostic.from_json(require_object(item))
                for item in require_list(data, "diagnostics")
            ],
            # Default to empty when the key is absent (a legacy/read-only outcome).
            room_narration=optional_str_list(data, "room_narration"),
            arrival_narration=optional_str_list(data, "arrival_narration"),
        )
