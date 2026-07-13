"""Sandboxed script request/result contracts — Python mirror of `script.rs`."""

from __future__ import annotations

from dataclasses import dataclass, field

from lorecraft.protocol.effects import Effect
from lorecraft.protocol.envelope import Diagnostic
from lorecraft.protocol.messages import OutboundMessage
from lorecraft.protocol.snapshot import EntitySnapshot
from lorecraft.types import JsonValue


@dataclass(frozen=True, slots=True)
class ScriptBudget:
    """Resource ceilings for a single script invocation."""

    wall_ms: int
    instructions: int
    memory_bytes: int
    output_bytes: int


@dataclass(frozen=True, slots=True)
class EmittedEvent:
    """A domain event emitted by a script. Intentionally minimal for this kickoff;
    expanded (routing, causality) in a later phase."""

    event_type: str
    payload: JsonValue


@dataclass(frozen=True, slots=True)
class ScheduledWork:
    """Work a script schedules for a future logical time. Intentionally minimal for
    this kickoff; expanded (recurrence, cancellation) in a later phase."""

    job_id: str
    due_logical_time: int
    payload: JsonValue


@dataclass(frozen=True, slots=True)
class ScriptRequest:
    """The fully-materialized input handed to a sandboxed script."""

    api_version: int
    script_id: str
    script_version: int
    command_or_event: str
    actor_snapshot: EntitySnapshot
    room_snapshot: EntitySnapshot
    selected_related_entities: list[EntitySnapshot] = field(default_factory=list)
    logical_time: int = 0
    rng_stream_id: str = ""
    capability_set: list[str] = field(default_factory=list)
    budget: ScriptBudget = field(
        default_factory=lambda: ScriptBudget(
            wall_ms=0, instructions=0, memory_bytes=0, output_bytes=0
        )
    )


@dataclass(frozen=True, slots=True)
class ScriptResult:
    """The result a script proposes back to the host. Nothing is applied until the
    engine validates it."""

    messages: list[OutboundMessage] = field(default_factory=list)
    proposed_effects: list[Effect] = field(default_factory=list)
    emitted_events: list[EmittedEvent] = field(default_factory=list)
    scheduled_work: list[ScheduledWork] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
