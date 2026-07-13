//! `execute.rs` — the Rust-owned execution driver for migrated verbs (Phase 4,
//! Option A).
//!
//! When [`crate::route::decide`] routes a command to Rust, this driver runs the
//! Option-A round-trip against the per-connection [`ForwardClient`] link: **Rust
//! owns execution, Python owns persistence** (migration-plan Decision 1). For a
//! migrated verb the conversation is:
//!
//! 1. [`ForwardClient::build_snapshot`] — send [`GatewayInbound::BuildSnapshot`]
//!    (`{envelope}`) and await the correlated [`GatewayOutbound::SnapshotReady`]
//!    ([`ScriptRequest`]). Python reads its repos and materializes the immutable
//!    snapshot; Rust holds no authoritative world state this phase (Decision 2).
//! 2. Run the migrated **feature** on that snapshot to derive the authoritative
//!    [`CommandOutcome`]. For `look` this is [`lorecraft_feature_look::look_effects`]
//!    — a pure, read-only function that proposes **zero effects**, so the outcome's
//!    `applied_effects` is empty (Rust "owns truth": there is nothing to validate
//!    or apply for a read-only verb).
//! 3. [`ForwardClient::apply_outcome`] — send [`GatewayInbound::ApplyOutcome`]
//!    (`{command_id, outcome}`) and await [`GatewayOutbound::OutcomeApplied`].
//!    Python persists the (here empty) effects, writes the audit row, commits both
//!    DBs, and returns the legacy `direct_reply` plus the fan-out deliveries.
//!
//! **Commit-before-publish is preserved (Decision 5):** Python commits *before*
//! emitting `OutcomeApplied`, and the [`ForwardClient`] read loop publishes that
//! frame's `deliveries` into the shared [`ConnectionRegistry`] only on receipt —
//! the same Phase 3 `Deliver` fan-out path a `CommandReply`'s deliveries take. The
//! driver itself returns only the issuing client's `direct_reply`; the fan-out is
//! already dispatched by the time it returns.
//!
//! ## Early short-circuit (Phase 4b hardening)
//!
//! Python can end the round-trip early at either await point by replying with a
//! [`GatewayOutbound::ExecutionRejected`] in place of `SnapshotReady`/`OutcomeApplied`
//! (a **frozen-session** rejection before execution, or a **persistence-handler
//! failure**). The driver then returns the carried client reply and runs no further
//! leg — no feature, no `ApplyOutcome`, no publish. This is what keeps a raised
//! Python handler or a frozen session from wedging the connection: paired with the
//! [`tokio::time::timeout`] backstop the caller wraps `execute` in (so even a peer
//! that sends *nothing* is bounded), the execution path can never hang.
//!
//! [`GatewayOutbound::ExecutionRejected`]: lorecraft_protocol::gateway::GatewayOutbound::ExecutionRejected
//!
//! ## Direct feature call vs. the runtime actor
//!
//! For 4a the driver calls the feature crate **directly**. The
//! [`WorldActor`](lorecraft_runtime::WorldActor) ordering/dispatch mechanism
//! (drain → sort by `(logical_time, receive_sequence)` → dispatch) is not on this
//! path: a per-connection `look` is a single, self-correlated round-trip with no
//! cross-command ordering to resolve, so routing it through the actor would add a
//! queue hop and a `CommandPolicy` shim without changing behavior. Wiring the actor
//! in as the ordered-dispatch front end is a clean later refinement (it becomes
//! load-bearing once a mutating, cross-actor verb like movement needs canonical
//! ordering across concurrent commands) and is noted as such rather than built now.
//!
//! [`GatewayInbound::BuildSnapshot`]: lorecraft_protocol::gateway::GatewayInbound::BuildSnapshot
//! [`GatewayInbound::ApplyOutcome`]: lorecraft_protocol::gateway::GatewayInbound::ApplyOutcome
//! [`GatewayOutbound::SnapshotReady`]: lorecraft_protocol::gateway::GatewayOutbound::SnapshotReady
//! [`GatewayOutbound::OutcomeApplied`]: lorecraft_protocol::gateway::GatewayOutbound::OutcomeApplied
//! [`ScriptRequest`]: lorecraft_protocol::script::ScriptRequest
//! [`ConnectionRegistry`]: lorecraft_events::ConnectionRegistry

use lorecraft_feature_move::{Direction, MoveDecision, MoveExecution, WARNING_MESSAGE_TYPE};
use lorecraft_protocol::envelope::{CommandEnvelope, CommandOutcome, OutcomeStatus};
use lorecraft_protocol::ids::CommandId;
use lorecraft_protocol::messages::OutboundMessage;

use crate::forward::{ForwardClient, ForwardError, SnapshotOutcome};
use crate::route::MigratedVerb;

/// Drive one Rust-routed command to its `direct_reply` over the Option-A
/// round-trip, dispatching on the resolved [`MigratedVerb`].
///
/// The returned value is the opaque legacy `command_result` for the issuing
/// client (identical in shape to [`ForwardClient::send_command`]'s reply), so the
/// caller ([`crate::ws_player`]) queues it back exactly as it does the Python path.
pub async fn execute(
    forward: &ForwardClient,
    verb: MigratedVerb,
    envelope: CommandEnvelope,
) -> Result<serde_json::Value, ForwardError> {
    match verb {
        MigratedVerb::Look => execute_look(forward, envelope).await,
        MigratedVerb::Move(direction) => execute_move(forward, direction, envelope).await,
    }
}

/// Execute a `look`: snapshot → run [`lorecraft_feature_look`] → apply outcome.
///
/// `look` is read-only, so the derived [`CommandOutcome`] carries the feature's
/// ordered `messages` and an **empty** `applied_effects` / `commit_sequence: None`
/// — there is no state mutation to persist, only the audit row + room broadcast
/// Python reproduces on `ApplyOutcome`.
async fn execute_look(
    forward: &ForwardClient,
    envelope: CommandEnvelope,
) -> Result<serde_json::Value, ForwardError> {
    let command_id = envelope.command_id.clone();
    // `look` is always Rust-executable, so Python never defers it; keep a copy only
    // so a stray `DeferToPython` can be handled defensively (re-forward) rather than
    // panicking the authoritative path.
    let forward_envelope = envelope.clone();

    // 1. Snapshot round-trip (Rust cannot read world state this phase). Python may
    //    short-circuit here — a frozen session or a snapshot-build failure returns
    //    `ExecutionRejected`, surfaced as `SnapshotOutcome::Rejected`. In that case
    //    we send the carried client reply and run NO feature, NO `ApplyOutcome`, NO
    //    audit, NO broadcast — byte-parity with the pure-Python frozen guard.
    let request = match forward.build_snapshot(envelope).await? {
        SnapshotOutcome::Ready(request) => request,
        SnapshotOutcome::Rejected(direct_reply) => return Ok(direct_reply),
        // `look` is never skill-gated; a defer here is a protocol anomaly — run the
        // command in Python rather than trust an unexpected snapshot decision.
        SnapshotOutcome::Defer => return forward.send_command(forward_envelope).await,
    };

    // 2. Run the migrated feature to derive the authoritative outcome.
    let result = lorecraft_feature_look::look_effects(&request);
    let outcome = look_outcome(command_id.clone(), result);

    // 3. Persist round-trip; Python commits before returning, then the read loop
    //    publishes the deliveries — commit-before-publish preserved. A persistence
    //    failure here also short-circuits to an in-game error reply (no publish).
    forward.apply_outcome(command_id, outcome).await
}

/// Map a `look` [`ScriptResult`](lorecraft_protocol::script::ScriptResult) to the
/// authoritative [`CommandOutcome`] Python persists.
///
/// Factored out (pure, no I/O) so the feature → outcome mapping is unit-testable
/// without a live link. `look` proposes zero effects, so `applied_effects` is empty
/// and `commit_sequence` is `None`; the ordered `messages` are carried verbatim.
fn look_outcome(
    command_id: CommandId,
    result: lorecraft_protocol::script::ScriptResult,
) -> CommandOutcome {
    CommandOutcome {
        command_id,
        status: OutcomeStatus::Executed,
        commit_sequence: None,
        messages: result.messages,
        // Read-only verb: nothing proposed, nothing to validate or apply.
        applied_effects: Vec::new(),
        diagnostics: Vec::new(),
        // Read-only verb: no room-directed narration.
        room_narration: Vec::new(),
        arrival_narration: Vec::new(),
    }
}

/// Execute a movement: snapshot → run [`lorecraft_feature_move`] → apply outcome,
/// **deferring to Python** for a skill-gated target (OPEN ITEM #3).
///
/// There are three terminal shapes, mirroring [`MoveDecision`]:
///
/// - **[`MoveDecision::Moved`]** — the derived [`CommandOutcome`] carries the actor's
///   `You go {dir}.` feed + `room_id` panel refresh, the single
///   [`Effect::MoveEntity`](lorecraft_protocol::Effect::MoveEntity) to persist, and
///   the origin/destination narration (`room_narration`/`arrival_narration`). Python
///   applies the move (`current_room_id`/`visited_rooms`, connection-map move,
///   `PLAYER_MOVED` flush) and broadcasts the narration.
/// - **[`MoveDecision::Blocked`]** — a warning-only outcome (no effects, no
///   narration); Python renders the warning + writes the audit row, exactly as the
///   pure-Python blocked move does.
/// - **[`MoveDecision::DeferToPython`]** — the whole command is re-forwarded to
///   Python (the ordinary Phase-3 path), keeping the terrain-skill RNG draw
///   Python-side. This also covers the Python-side `DeferToPython` short-circuit
///   ([`SnapshotOutcome::Defer`]): both converge on running the command in Python.
async fn execute_move(
    forward: &ForwardClient,
    direction: Direction,
    envelope: CommandEnvelope,
) -> Result<serde_json::Value, ForwardError> {
    let command_id = envelope.command_id.clone();
    // Keep a copy to re-forward if execution must defer to Python (skill-gated
    // move / Python `DeferToPython`); `build_snapshot` consumes the envelope.
    let forward_envelope = envelope.clone();

    let request = match forward.build_snapshot(envelope).await? {
        SnapshotOutcome::Ready(request) => request,
        SnapshotOutcome::Rejected(direct_reply) => return Ok(direct_reply),
        // Python declined to build a snapshot (skill-gated target): run the whole
        // command in Python via the ordinary forward path.
        SnapshotOutcome::Defer => return forward.send_command(forward_envelope).await,
    };

    match lorecraft_feature_move::move_effects(direction, &request) {
        // Belt-and-suspenders: if a skill-gated snapshot ever reaches Rust, defer
        // rather than execute — the RNG draw must stay in Python (OPEN ITEM #3).
        MoveDecision::DeferToPython => forward.send_command(forward_envelope).await,
        decision => {
            let outcome = move_outcome(command_id.clone(), decision);
            forward.apply_outcome(command_id, outcome).await
        }
    }
}

/// Map a non-deferred [`MoveDecision`] to the authoritative [`CommandOutcome`] Python
/// persists. Pure (no I/O) so the decision → outcome mapping is unit-testable.
///
/// # Panics
/// Never in practice: [`execute_move`] handles [`MoveDecision::DeferToPython`] before
/// calling this, so only `Moved`/`Blocked` reach here. The exhaustive `match` documents
/// that invariant rather than a silent catch-all.
fn move_outcome(command_id: CommandId, decision: MoveDecision) -> CommandOutcome {
    match decision {
        MoveDecision::Moved(MoveExecution {
            actor_messages,
            effect,
            room_narration,
            arrival_narration,
        }) => CommandOutcome {
            command_id,
            status: OutcomeStatus::Executed,
            commit_sequence: None,
            messages: actor_messages,
            applied_effects: vec![effect],
            diagnostics: Vec::new(),
            room_narration: vec![room_narration],
            arrival_narration: vec![arrival_narration],
        },
        MoveDecision::Blocked { message } => CommandOutcome {
            command_id,
            status: OutcomeStatus::Blocked,
            commit_sequence: None,
            messages: vec![OutboundMessage::Feed {
                text: message,
                message_type: WARNING_MESSAGE_TYPE.into(),
            }],
            // A blocked move mutates nothing and narrates nothing to the room.
            applied_effects: Vec::new(),
            diagnostics: Vec::new(),
            room_narration: Vec::new(),
            arrival_narration: Vec::new(),
        },
        // `execute_move` never routes a defer here (it re-forwards instead); this arm
        // keeps the match exhaustive without a catch-all that could mask a new variant.
        MoveDecision::DeferToPython => unreachable!(
            "execute_move handles DeferToPython by re-forwarding before mapping an outcome"
        ),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use lorecraft_protocol::messages::OutboundMessage;
    use lorecraft_protocol::script::{ScriptBudget, ScriptRequest};
    use lorecraft_protocol::snapshot::EntitySnapshot;
    use std::collections::BTreeMap;

    fn look_request() -> ScriptRequest {
        let mut attrs: BTreeMap<String, serde_json::Value> = BTreeMap::new();
        attrs.insert("name".into(), serde_json::json!("The Tavern"));
        attrs.insert("description".into(), serde_json::json!("A cozy room."));
        attrs.insert("exits".into(), serde_json::json!(["north"]));
        ScriptRequest {
            api_version: 1,
            script_id: "look".into(),
            script_version: 1,
            command_or_event: "look".into(),
            actor_snapshot: EntitySnapshot {
                id: "player-1".into(),
                kind: "player".into(),
                attributes: BTreeMap::new(),
            },
            room_snapshot: EntitySnapshot {
                id: "tavern".into(),
                kind: "room".into(),
                attributes: attrs,
            },
            selected_related_entities: vec![],
            logical_time: 0,
            rng_stream_id: String::new(),
            capability_set: vec![],
            budget: ScriptBudget {
                wall_ms: 0,
                instructions: 0,
                memory_bytes: 0,
                output_bytes: 0,
            },
        }
    }

    fn move_request(username: &str) -> ScriptRequest {
        let mut exit: serde_json::Map<String, serde_json::Value> = serde_json::Map::new();
        exit.insert("target_room_id".into(), serde_json::json!("north_road"));
        exit.insert("target_active".into(), serde_json::json!(true));
        let mut exits: serde_json::Map<String, serde_json::Value> = serde_json::Map::new();
        exits.insert("north".into(), serde_json::Value::Object(exit));
        let mut room_attrs: BTreeMap<String, serde_json::Value> = BTreeMap::new();
        room_attrs.insert("exits".into(), serde_json::Value::Object(exits));
        let mut actor_attrs: BTreeMap<String, serde_json::Value> = BTreeMap::new();
        actor_attrs.insert("username".into(), serde_json::json!(username));
        ScriptRequest {
            api_version: 1,
            script_id: "movement".into(),
            script_version: 1,
            command_or_event: "go".into(),
            actor_snapshot: EntitySnapshot {
                id: "player-1".into(),
                kind: "player".into(),
                attributes: actor_attrs,
            },
            room_snapshot: EntitySnapshot {
                id: "village_square".into(),
                kind: "room".into(),
                attributes: room_attrs,
            },
            selected_related_entities: vec![],
            logical_time: 0,
            rng_stream_id: String::new(),
            capability_set: vec![],
            budget: ScriptBudget {
                wall_ms: 0,
                instructions: 0,
                memory_bytes: 0,
                output_bytes: 0,
            },
        }
    }

    #[test]
    fn move_outcome_maps_moved_to_effect_narration_and_messages() {
        let request = move_request("Aldric");
        let decision = lorecraft_feature_move::move_effects(Direction::North, &request);
        let outcome = move_outcome(CommandId("cmd-1".into()), decision);

        assert_eq!(outcome.status, OutcomeStatus::Executed);
        assert_eq!(
            outcome.applied_effects,
            vec![lorecraft_protocol::Effect::MoveEntity {
                entity: "player-1".into(),
                from: "village_square".into(),
                to: "north_road".into(),
            }]
        );
        // The room-directed narration rides on the additive outcome fields.
        assert_eq!(outcome.room_narration, vec!["Aldric leaves north."]);
        assert_eq!(
            outcome.arrival_narration,
            vec!["Aldric arrives from the south."]
        );
        // The actor's own feed opens with the "You go north." line.
        assert!(matches!(
            outcome.messages.first(),
            Some(OutboundMessage::Feed { text, .. }) if text == "You go north."
        ));
    }

    #[test]
    fn move_outcome_maps_blocked_to_warning_only() {
        // No exit south → a Blocked decision → a warning-only, no-effect outcome.
        let request = move_request("Aldric");
        let decision = lorecraft_feature_move::move_effects(Direction::South, &request);
        let outcome = move_outcome(CommandId("cmd-2".into()), decision);

        assert_eq!(outcome.status, OutcomeStatus::Blocked);
        assert!(outcome.applied_effects.is_empty());
        assert!(outcome.room_narration.is_empty());
        assert!(outcome.arrival_narration.is_empty());
        assert_eq!(
            outcome.messages,
            vec![OutboundMessage::Feed {
                text: "You can't go that way.".into(),
                message_type: "warning".into(),
            }]
        );
    }

    #[test]
    fn look_outcome_is_read_only_and_carries_the_feature_messages() {
        let request = look_request();
        let result = lorecraft_feature_look::look_effects(&request);
        // Sanity: the feature really is read-only.
        assert!(result.proposed_effects.is_empty());
        let expected_messages = result.messages.clone();

        let outcome = look_outcome(CommandId("cmd-1".into()), result);

        assert_eq!(outcome.command_id, CommandId("cmd-1".into()));
        assert_eq!(outcome.status, OutcomeStatus::Executed);
        assert_eq!(outcome.commit_sequence, None);
        assert!(
            outcome.applied_effects.is_empty(),
            "look derives no effects to apply"
        );
        assert!(outcome.diagnostics.is_empty());
        // The ordered feature output is carried verbatim (Feed lines + the trailing
        // room_id PanelUpdate).
        assert_eq!(outcome.messages, expected_messages);
        assert!(matches!(
            outcome.messages.last(),
            Some(OutboundMessage::PanelUpdate { key, .. }) if key == "room_id"
        ));
    }
}
