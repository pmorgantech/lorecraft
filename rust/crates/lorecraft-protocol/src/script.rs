//! Sandboxed script invocation request/result contracts.

use serde::{Deserialize, Serialize};

use crate::effects::Effect;
use crate::envelope::Diagnostic;
use crate::messages::OutboundMessage;
use crate::snapshot::EntitySnapshot;

/// Resource ceilings for a single script invocation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScriptBudget {
    /// Wall-clock ceiling in milliseconds.
    pub wall_ms: u64,
    /// Maximum interpreter instructions.
    pub instructions: u64,
    /// Maximum heap bytes.
    pub memory_bytes: u64,
    /// Maximum output bytes.
    pub output_bytes: u64,
}

/// A domain event emitted by a script for downstream handling.
///
/// Intentionally minimal for this kickoff — expanded (routing, causality) in a
/// later phase.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EmittedEvent {
    /// Event type name.
    pub event_type: String,
    /// Arbitrary event payload.
    pub payload: serde_json::Value,
}

/// Work a script schedules to run at a future logical time.
///
/// Intentionally minimal for this kickoff — expanded (recurrence, cancellation)
/// in a later phase.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ScheduledWork {
    /// Identifier of the scheduled job.
    pub job_id: String,
    /// Logical time at which the job becomes due.
    pub due_logical_time: u64,
    /// Arbitrary job payload.
    pub payload: serde_json::Value,
}

/// The fully-materialized input handed to a sandboxed script.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ScriptRequest {
    /// Script API version the host provides.
    pub api_version: u32,
    /// Identifier of the script being invoked.
    pub script_id: String,
    /// Version of the script's source.
    pub script_version: u32,
    /// The command verb or event name that triggered this invocation.
    pub command_or_event: String,
    /// Snapshot of the acting entity.
    pub actor_snapshot: EntitySnapshot,
    /// Snapshot of the room context.
    pub room_snapshot: EntitySnapshot,
    /// Additional entities the host selected as relevant (e.g. room items).
    pub selected_related_entities: Vec<EntitySnapshot>,
    /// Deterministic logical clock value for this invocation.
    pub logical_time: u64,
    /// Identifier of the RNG stream the script may draw from.
    pub rng_stream_id: String,
    /// Capabilities granted to this invocation.
    pub capability_set: Vec<String>,
    /// Resource budget for this invocation.
    pub budget: ScriptBudget,
}

/// The result a script proposes back to the host. Nothing here is applied until
/// the engine validates it.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ScriptResult {
    /// Messages to deliver to the client, in order.
    pub messages: Vec<OutboundMessage>,
    /// State-change effects proposed (subject to engine validation).
    pub proposed_effects: Vec<Effect>,
    /// Domain events emitted.
    pub emitted_events: Vec<EmittedEvent>,
    /// Future work scheduled.
    pub scheduled_work: Vec<ScheduledWork>,
    /// Diagnostics produced during evaluation.
    pub diagnostics: Vec<Diagnostic>,
}
