//! Outbound messages delivered to a client as part of a command outcome.

use serde::{Deserialize, Serialize};

/// A message sent to a client. Serialized as an internally-tagged object with a
/// `"type"` discriminator (e.g. `{"type": "Feed", ...}`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum OutboundMessage {
    /// A narrative feed line — maps to the Python engine's `ctx.say`.
    Feed {
        /// Line text.
        text: String,
        /// Message-type tag (routing/styling hint), e.g. `"system"`.
        message_type: String,
    },
    /// A client panel refresh keyed by panel name — maps to `ctx.push_update`.
    /// This is a client-side refresh hint, not an authoritative state change.
    PanelUpdate {
        /// Panel key, e.g. `"room_id"`.
        key: String,
        /// New panel value.
        value: serde_json::Value,
    },
}
