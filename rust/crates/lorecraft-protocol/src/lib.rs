//! Lorecraft protocol types — IDs, envelopes, versioning, and scripting boundaries.
//!
//! This crate defines the value-oriented contracts between engine, persistence, and
//! scripting layers. Types are versioned and serializable for replay, audit, and
//! cross-process communication.
//!
//! A field-for-field Python mirror lives in `src/lorecraft/protocol/`; the two are
//! kept in agreement by a shared JSON wire shape (transparent ID strings, tagged
//! effect/message enums) and a cross-language version drift-test.

#![warn(missing_docs)]

use serde::{Deserialize, Serialize};
use std::fmt;

pub mod effects;
pub mod envelope;
pub mod ids;
pub mod messages;
pub mod script;
pub mod snapshot;

pub use effects::Effect;
pub use envelope::{CommandEnvelope, CommandOutcome, Diagnostic, OutcomeStatus};
pub use ids::{ActorId, CommandId, PlayerId, SessionId, WorldId};
pub use messages::OutboundMessage;
pub use script::{EmittedEvent, ScheduledWork, ScriptBudget, ScriptRequest, ScriptResult};
pub use snapshot::EntitySnapshot;

/// Protocol version for this release.
pub const PROTOCOL_VERSION: u32 = 1;

/// A placeholder error type for protocol operations.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ProtocolError {
    /// Serialization or deserialization error
    SerializationError(String),
    /// Version mismatch
    VersionMismatch {
        /// Version the reader expected.
        expected: u32,
        /// Version actually received.
        got: u32,
    },
    /// Invalid command envelope
    InvalidEnvelope(String),
}

impl fmt::Display for ProtocolError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ProtocolError::SerializationError(msg) => write!(f, "Serialization error: {}", msg),
            ProtocolError::VersionMismatch { expected, got } => {
                write!(f, "Version mismatch: expected {}, got {}", expected, got)
            }
            ProtocolError::InvalidEnvelope(msg) => write!(f, "Invalid envelope: {}", msg),
        }
    }
}

impl std::error::Error for ProtocolError {}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::envelope::{CommandEnvelope, Diagnostic};
    use crate::ids::{ActorId, CommandId, PlayerId, SessionId, WorldId};
    use serde_json::json;
    use std::collections::BTreeMap;

    #[test]
    fn protocol_version_is_stable() {
        assert_eq!(PROTOCOL_VERSION, 1);
    }

    /// The checked-in schema file must agree with the compiled constant so drift
    /// is caught by `cargo test` (mirrored by the Python parity drift-test).
    #[test]
    fn schema_version_file_matches_constant() {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/schema/version.json");
        let raw = std::fs::read_to_string(path).expect("schema/version.json must exist");
        let parsed: serde_json::Value =
            serde_json::from_str(&raw).expect("schema/version.json must be valid JSON");
        assert_eq!(
            parsed["protocol_version"].as_u64(),
            Some(u64::from(PROTOCOL_VERSION)),
        );
    }

    fn sample_envelope() -> CommandEnvelope {
        CommandEnvelope {
            protocol_version: PROTOCOL_VERSION,
            world_id: WorldId("world-1".into()),
            actor_id: ActorId("actor-1".into()),
            player_id: PlayerId("player-1".into()),
            session_id: SessionId("session-1".into()),
            command_id: CommandId("cmd-1".into()),
            receive_sequence: 42,
            deadline_ms: 5_000,
            raw: "look".into(),
        }
    }

    fn assert_round_trip<T>(value: &T)
    where
        T: Serialize + for<'de> Deserialize<'de> + PartialEq + std::fmt::Debug,
    {
        let text = serde_json::to_string(value).expect("serialize");
        let back: T = serde_json::from_str(&text).expect("deserialize");
        assert_eq!(*value, back);
    }

    #[test]
    fn id_newtypes_serialize_transparently() {
        let id = WorldId("world-1".into());
        assert_eq!(serde_json::to_string(&id).unwrap(), "\"world-1\"");
        let back: WorldId = serde_json::from_str("\"world-1\"").unwrap();
        assert_eq!(id, back);
    }

    #[test]
    fn command_envelope_round_trips() {
        assert_round_trip(&sample_envelope());
    }

    #[test]
    fn script_request_round_trips() {
        let mut attrs: BTreeMap<String, serde_json::Value> = BTreeMap::new();
        attrs.insert("name".into(), json!("Tavern"));
        attrs.insert("exits".into(), json!(["north", "south"]));
        attrs.insert("nested".into(), json!({"a": [1, 2, {"b": true}]}));
        let room = EntitySnapshot {
            id: "tavern".into(),
            kind: "room".into(),
            attributes: attrs.clone(),
        };
        let actor = EntitySnapshot {
            id: "player-1".into(),
            kind: "player".into(),
            attributes: BTreeMap::new(),
        };
        let request = ScriptRequest {
            api_version: 1,
            script_id: "look".into(),
            script_version: 1,
            command_or_event: "look".into(),
            actor_snapshot: actor,
            room_snapshot: room,
            selected_related_entities: vec![EntitySnapshot {
                id: "old_sword".into(),
                kind: "item".into(),
                attributes: BTreeMap::new(),
            }],
            logical_time: 7,
            rng_stream_id: "stream-1".into(),
            capability_set: vec!["read".into()],
            budget: ScriptBudget {
                wall_ms: 50,
                instructions: 100_000,
                memory_bytes: 1_048_576,
                output_bytes: 65_536,
            },
        };
        assert_round_trip(&request);
    }

    #[test]
    fn entity_snapshot_attributes_round_trip_arbitrary_json() {
        let mut attrs: BTreeMap<String, serde_json::Value> = BTreeMap::new();
        attrs.insert("scalar".into(), json!(3));
        attrs.insert("string".into(), json!("x"));
        attrs.insert("list".into(), json!([1, "two", false, null]));
        attrs.insert("object".into(), json!({"deep": {"deeper": [true, 1.0]}}));
        let snap = EntitySnapshot {
            id: "e1".into(),
            kind: "thing".into(),
            attributes: attrs,
        };
        assert_round_trip(&snap);
    }

    #[test]
    fn script_result_round_trips() {
        let result = ScriptResult {
            messages: vec![OutboundMessage::Feed {
                text: "Tavern".into(),
                message_type: "system".into(),
            }],
            proposed_effects: vec![],
            emitted_events: vec![EmittedEvent {
                event_type: "looked".into(),
                payload: json!({"room": "tavern"}),
            }],
            scheduled_work: vec![ScheduledWork {
                job_id: "job-1".into(),
                due_logical_time: 99,
                payload: json!(null),
            }],
            diagnostics: vec![Diagnostic {
                level: "info".into(),
                message: "ok".into(),
            }],
        };
        assert_round_trip(&result);
    }

    #[test]
    fn command_outcome_round_trips() {
        let outcome = CommandOutcome {
            command_id: CommandId("cmd-1".into()),
            status: OutcomeStatus::Executed,
            commit_sequence: Some(3),
            messages: vec![OutboundMessage::PanelUpdate {
                key: "room_id".into(),
                value: json!("tavern"),
            }],
            applied_effects: vec![],
            diagnostics: vec![],
        };
        assert_round_trip(&outcome);
    }

    #[test]
    fn each_effect_variant_round_trips_and_tags() {
        let cases: Vec<(Effect, &str)> = vec![
            (
                Effect::MoveEntity {
                    entity: "e".into(),
                    from: "a".into(),
                    to: "b".into(),
                },
                "MoveEntity",
            ),
            (
                Effect::TransferItem {
                    item: "coin".into(),
                    from: "room".into(),
                    to: "player".into(),
                    quantity: 2,
                },
                "TransferItem",
            ),
            (
                Effect::AdjustMeter {
                    entity: "p".into(),
                    meter: "health".into(),
                    delta: -5,
                },
                "AdjustMeter",
            ),
            (
                Effect::SetFlag {
                    entity: "p".into(),
                    key: "seen".into(),
                    value: json!(true),
                },
                "SetFlag",
            ),
            (
                Effect::EmitEvent {
                    event_type: "boom".into(),
                    payload: json!({"n": 1}),
                },
                "EmitEvent",
            ),
            (
                Effect::SendNarration {
                    text: "x".into(),
                    message_type: "feed".into(),
                },
                "SendNarration",
            ),
        ];
        for (effect, tag) in cases {
            let value: serde_json::Value = serde_json::to_value(&effect).unwrap();
            assert_eq!(value["type"], json!(tag));
            assert_round_trip(&effect);
        }
    }

    #[test]
    fn send_narration_serializes_to_expected_shape() {
        let effect = Effect::SendNarration {
            text: "x".into(),
            message_type: "feed".into(),
        };
        let value: serde_json::Value = serde_json::to_value(&effect).unwrap();
        assert_eq!(
            value,
            json!({"type": "SendNarration", "text": "x", "message_type": "feed"})
        );
    }

    #[test]
    fn each_outbound_message_variant_round_trips_and_tags() {
        let feed = OutboundMessage::Feed {
            text: "hi".into(),
            message_type: "system".into(),
        };
        assert_eq!(
            serde_json::to_value(&feed).unwrap(),
            json!({"type": "Feed", "text": "hi", "message_type": "system"})
        );
        assert_round_trip(&feed);

        let panel = OutboundMessage::PanelUpdate {
            key: "room_id".into(),
            value: json!("tavern"),
        };
        assert_eq!(
            serde_json::to_value(&panel).unwrap(),
            json!({"type": "PanelUpdate", "key": "room_id", "value": "tavern"})
        );
        assert_round_trip(&panel);
    }
}
