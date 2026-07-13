//! Authoritative state-change effects proposed by scripts and applied by the engine.

use serde::{Deserialize, Serialize};

/// A single authoritative state change.
///
/// Effects are the only sanctioned way a script proposes a mutation; the engine
/// validates and applies them. This is the minimal kickoff set — more variants are
/// added as later migration slices need them. Serialized as an internally-tagged
/// object with a `"type"` discriminator (e.g. `{"type": "MoveEntity", ...}`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum Effect {
    /// Move an entity from one container/location to another.
    MoveEntity {
        /// The entity being moved.
        entity: String,
        /// Source location id.
        from: String,
        /// Destination location id.
        to: String,
    },
    /// Transfer a quantity of an item between two owners/locations.
    TransferItem {
        /// The item being transferred.
        item: String,
        /// Source owner/location id.
        from: String,
        /// Destination owner/location id.
        to: String,
        /// Number of units transferred.
        quantity: u32,
    },
    /// Adjust a numeric meter (e.g. health, coins) by a signed delta.
    AdjustMeter {
        /// The entity whose meter changes.
        entity: String,
        /// Meter name.
        meter: String,
        /// Signed change applied to the meter.
        delta: i64,
    },
    /// Set (or overwrite) a flag on an entity to an arbitrary JSON value.
    SetFlag {
        /// The entity carrying the flag.
        entity: String,
        /// Flag key.
        key: String,
        /// New flag value.
        value: serde_json::Value,
    },
    /// Emit a domain event for downstream handlers.
    EmitEvent {
        /// Event type name.
        event_type: String,
        /// Arbitrary event payload.
        payload: serde_json::Value,
    },
    /// Emit narration ordered relative to state effects (for scripts/events that
    /// need text interleaved with mutations). Command handlers narrate through
    /// [`crate::OutboundMessage::Feed`] instead.
    SendNarration {
        /// Narration text.
        text: String,
        /// Message-type tag (routing/styling hint).
        message_type: String,
    },
}
