"""Command ingress envelope and outcome — Python mirror of `envelope.rs`.

ID fields are plain `str` aliases (matching the Rust `#[serde(transparent)]`
newtypes' bare-string JSON), so no wrapping is needed on this side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from lorecraft.protocol.effects import Effect
from lorecraft.protocol.messages import OutboundMessage

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


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """The authoritative result of executing a ``CommandEnvelope``."""

    command_id: CommandId
    status: OutcomeStatus
    commit_sequence: int | None = None
    messages: list[OutboundMessage] = field(default_factory=list)
    applied_effects: list[Effect] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
