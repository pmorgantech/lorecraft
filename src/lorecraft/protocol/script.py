"""Sandboxed script request/result contracts — Python mirror of `script.rs`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from lorecraft.protocol._coerce import (
    require_int,
    require_list,
    require_object,
    require_str,
    require_str_list,
)
from lorecraft.protocol.effects import Effect, effect_from_json
from lorecraft.protocol.envelope import Diagnostic
from lorecraft.protocol.messages import OutboundMessage, message_from_json
from lorecraft.protocol.snapshot import EntitySnapshot
from lorecraft.types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class ScriptBudget:
    """Resource ceilings for a single script invocation."""

    wall_ms: int
    instructions: int
    memory_bytes: int
    output_bytes: int

    def to_json(self) -> JsonObject:
        return {
            "wall_ms": self.wall_ms,
            "instructions": self.instructions,
            "memory_bytes": self.memory_bytes,
            "output_bytes": self.output_bytes,
        }

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        return cls(
            wall_ms=require_int(data, "wall_ms"),
            instructions=require_int(data, "instructions"),
            memory_bytes=require_int(data, "memory_bytes"),
            output_bytes=require_int(data, "output_bytes"),
        )


@dataclass(frozen=True, slots=True)
class EmittedEvent:
    """A domain event emitted by a script. Intentionally minimal for this kickoff;
    expanded (routing, causality) in a later phase."""

    event_type: str
    payload: JsonValue

    def to_json(self) -> JsonObject:
        return {"event_type": self.event_type, "payload": self.payload}

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        return cls(
            event_type=require_str(data, "event_type"), payload=data.get("payload")
        )


@dataclass(frozen=True, slots=True)
class ScheduledWork:
    """Work a script schedules for a future logical time. Intentionally minimal for
    this kickoff; expanded (recurrence, cancellation) in a later phase."""

    job_id: str
    due_logical_time: int
    payload: JsonValue

    def to_json(self) -> JsonObject:
        return {
            "job_id": self.job_id,
            "due_logical_time": self.due_logical_time,
            "payload": self.payload,
        }

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        return cls(
            job_id=require_str(data, "job_id"),
            due_logical_time=require_int(data, "due_logical_time"),
            payload=data.get("payload"),
        )


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

    def to_json(self) -> JsonObject:
        return {
            "api_version": self.api_version,
            "script_id": self.script_id,
            "script_version": self.script_version,
            "command_or_event": self.command_or_event,
            "actor_snapshot": self.actor_snapshot.to_json(),
            "room_snapshot": self.room_snapshot.to_json(),
            "selected_related_entities": [
                snapshot.to_json() for snapshot in self.selected_related_entities
            ],
            "logical_time": self.logical_time,
            "rng_stream_id": self.rng_stream_id,
            "capability_set": list(self.capability_set),
            "budget": self.budget.to_json(),
        }

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        return cls(
            api_version=require_int(data, "api_version"),
            script_id=require_str(data, "script_id"),
            script_version=require_int(data, "script_version"),
            command_or_event=require_str(data, "command_or_event"),
            actor_snapshot=EntitySnapshot.from_json(
                require_object(data.get("actor_snapshot"))
            ),
            room_snapshot=EntitySnapshot.from_json(
                require_object(data.get("room_snapshot"))
            ),
            selected_related_entities=[
                EntitySnapshot.from_json(require_object(item))
                for item in require_list(data, "selected_related_entities")
            ],
            logical_time=require_int(data, "logical_time"),
            rng_stream_id=require_str(data, "rng_stream_id"),
            capability_set=require_str_list(data, "capability_set"),
            budget=ScriptBudget.from_json(require_object(data.get("budget"))),
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

    def to_json(self) -> JsonObject:
        # Nested messages/effects keep their own ``{"type": ...}`` tags — recurse
        # through each element's ``to_json`` rather than a flat ``asdict``.
        return {
            "messages": [message.to_json() for message in self.messages],
            "proposed_effects": [effect.to_json() for effect in self.proposed_effects],
            "emitted_events": [event.to_json() for event in self.emitted_events],
            "scheduled_work": [work.to_json() for work in self.scheduled_work],
            "diagnostics": [diagnostic.to_json() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        return cls(
            messages=[
                message_from_json(require_object(item))
                for item in require_list(data, "messages")
            ],
            proposed_effects=[
                effect_from_json(require_object(item))
                for item in require_list(data, "proposed_effects")
            ],
            emitted_events=[
                EmittedEvent.from_json(require_object(item))
                for item in require_list(data, "emitted_events")
            ],
            scheduled_work=[
                ScheduledWork.from_json(require_object(item))
                for item in require_list(data, "scheduled_work")
            ],
            diagnostics=[
                Diagnostic.from_json(require_object(item))
                for item in require_list(data, "diagnostics")
            ],
        )
