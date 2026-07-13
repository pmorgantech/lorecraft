//! Command ingress envelope and execution outcome.

use serde::{Deserialize, Serialize};

use crate::effects::Effect;
use crate::ids::{ActorId, CommandId, PlayerId, SessionId, WorldId};
use crate::messages::OutboundMessage;

/// A command as admitted to the engine, carrying all routing/idempotency metadata.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CommandEnvelope {
    /// Protocol version the envelope was produced under.
    pub protocol_version: u32,
    /// World the command targets.
    pub world_id: WorldId,
    /// Actor issuing the command.
    pub actor_id: ActorId,
    /// Player account behind the actor.
    pub player_id: PlayerId,
    /// Session/connection the command arrived on.
    pub session_id: SessionId,
    /// Idempotency key for this command.
    pub command_id: CommandId,
    /// Monotonic admission/client sequence number.
    pub receive_sequence: u64,
    /// Monotonic execution budget in milliseconds.
    pub deadline_ms: u64,
    /// Raw command line as typed by the player.
    pub raw: String,
}

/// Terminal status of a command's execution.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum OutcomeStatus {
    /// Command ran and committed successfully.
    Executed,
    /// Command was rejected before mutation (a rule/precondition blocked it).
    Blocked,
    /// Command failed during execution.
    Failed,
    /// Command exceeded its execution deadline.
    TimedOut,
}

/// A diagnostic annotation attached to an outcome or script result.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Diagnostic {
    /// Severity/category label, e.g. `"info"`, `"warning"`, `"error"`.
    pub level: String,
    /// Human-readable diagnostic message.
    pub message: String,
}

/// The authoritative result of executing a [`CommandEnvelope`].
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CommandOutcome {
    /// Command this outcome corresponds to.
    pub command_id: CommandId,
    /// Terminal status.
    pub status: OutcomeStatus,
    /// Commit sequence assigned if the command committed state, else `None`.
    pub commit_sequence: Option<u64>,
    /// Messages to deliver to the client, in order.
    pub messages: Vec<OutboundMessage>,
    /// Effects the engine actually applied.
    pub applied_effects: Vec<Effect>,
    /// Diagnostics produced during execution.
    pub diagnostics: Vec<Diagnostic>,
}
