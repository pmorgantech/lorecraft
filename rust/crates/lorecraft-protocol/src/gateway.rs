//! Gateway framing protocol — the Rust↔Python transport envelopes for Phase 3.
//!
//! The Rust gateway owns client sockets; the Python app runs a UDS listener (the
//! "gateway adapter"). These two internally-tagged enums are the frames exchanged
//! over that channel: [`GatewayInbound`] (Rust→Python) and [`GatewayOutbound`]
//! (Python→Rust). Like [`crate::messages::OutboundMessage`] and [`crate::Effect`]
//! they serialize as `{"type": "...", ...}` objects, and a field-for-field Python
//! mirror lives in `src/lorecraft/protocol/gateway.py`.
//!
//! This module is **additive** — [`CommandEnvelope`] and every existing protocol
//! type are reused verbatim and unchanged. A forwarded command is carried as the
//! [`GatewayInbound::Command`] newtype variant wrapping an unmodified envelope.
//!
//! ## Resolved design decisions (Phase 3 kickoff spec, 2026-07-13)
//!
//! The design spec left some field shapes to Backend Engineering; they are
//! resolved here so the Rust client can harden around them:
//!
//! - **OPEN ITEM 1 — request/reply correlation.** Python emits both synchronous
//!   [`GatewayOutbound::CommandReply`] frames and unsolicited
//!   [`GatewayOutbound::Deliver`] pushes (clock ticks, weather, cross-player
//!   follow deliveries) multiplexed on the same UDS connection. Per the spec's own
//!   recommendation ("a correlation id on request/reply frames and un-correlated
//!   `Deliver` frames"), `CommandReply` carries a [`CommandId`] correlating it back
//!   to the originating [`GatewayInbound::Command`], while `Deliver` carries no
//!   correlation id because it is not a reply to any specific inbound frame.
//! - **`DeliveryDirective.payload` is an opaque relay.** Neither Rust nor Python
//!   interprets it; it preserves the legacy WebSocket frame shapes byte-exactly
//!   (spec decision 4). Convergence with [`crate::messages::OutboundMessage`] is
//!   deferred to Phase 4+.
//! - **Room ids are plain `String`.** There is no `RoomId` newtype in
//!   [`crate::ids`]; [`DeliveryTarget::Room`] and [`GatewayOutbound::ConnectAck`]
//!   use bare `String` room ids to match.
//!
//! ## Resolved admin-push design (Phase 3c, 2026-07-13)
//!
//! The admin console (`/admin/ws`) is a **push-only** channel: Python's
//! `AdminBroadcaster.push` fans one opaque frame out to *every* connected admin
//! socket (see `webui/admin/websocket.py`). Phase 3c moves that channel onto the
//! gateway; the additive protocol surface it needs is resolved here:
//!
//! - **Admin fan-out reuses [`GatewayOutbound::Deliver`].** A new
//!   [`DeliveryTarget::Admin`] unit variant (`{"type": "Admin"}`) names "every
//!   connected admin console." Python's broadcaster pushes an admin event as a
//!   normal `Deliver { DeliveryDirective { target: Admin, exclude, payload } }`
//!   frame and Rust resolves `Admin` against its admin registry, relaying the
//!   opaque `payload` exactly as it does `Room`/`Global` against the player
//!   registry. No separate parallel admin-deliver frame is introduced — the
//!   directive shape already generalizes cleanly.
//! - **Admin auth is a shape-distinct [`GatewayOutbound::AdminAuthResult`].** A
//!   validated admin carries **no** `player_id` (admin tokens are not player-
//!   scoped). Rather than overload the player [`GatewayOutbound::AuthResult`] with
//!   an ambiguous `accepted: true, player_id: None`, admin validation replies with
//!   a dedicated `AdminAuthResult { accepted }` frame that has no `player_id` field
//!   at all. This makes the two auth outcomes non-ambiguous by construction: the
//!   Rust `ws_admin` handshake matches on `AdminAuthResult` and a validated admin
//!   is *structurally* incapable of being fed into the player `Connected`/session
//!   path (which requires a `PlayerId`). The player `AuthResult` shape is untouched.
//! - **Admin lifecycle is Rust-local — no protocol frame.** Unlike players (who go
//!   through Python's `SessionSafetyService` grace/flicker handling via
//!   [`GatewayInbound::Connected`]/[`GatewayInbound::Disconnected`]), admin
//!   connections are stateless and push-only: Python holds no per-admin session
//!   state. Rust therefore owns the admin registry entirely — register on socket
//!   connect *after* an accepted `AdminAuthResult`, deregister on socket close —
//!   and Python is never told about admin connect/disconnect. No admin analogue of
//!   the `Connected`/`Disconnected` frames is added.
//!
//! ## Phase 4 execution round-trip (Option A, 2026-07-13)
//!
//! Phase 4 makes Rust the **authority for a slice of gameplay** for a migrated verb
//! (`look` first, then movement). Per the migration plan's **Decision 1 (Option A,
//! CONFIRMED)**, ownership is split: **Rust owns execution** (parse -> validate ->
//! effect derivation -> [`CommandOutcome`]) and **Python owns persistence** (applies
//! the effects through the existing repos/services, commits both the game and audit
//! SQLite databases, and returns the legacy deliveries). `lorecraft-store` stays a
//! stub this phase; full Rust DB ownership (Option B) is deferred to Phase 5.
//!
//! Because Rust holds no authoritative world state yet (**Decision 2**), it cannot
//! read player/room rows directly. So the migrated verb executes as a two round-trip
//! conversation over this same channel, added by the four **additive** frames below:
//!
//! 1. **[`GatewayInbound::BuildSnapshot`]** (Rust->Python): given the routed
//!    [`CommandEnvelope`], "build me the [`ScriptRequest`] snapshot to execute this
//!    verb." Python reads the repos and materializes the immutable snapshot.
//! 2. **[`GatewayOutbound::SnapshotReady`]** (Python->Rust): the snapshot, correlated
//!    by `command_id` (= the originating envelope's [`CommandId`]). Rust runs the
//!    feature against it and derives a [`CommandOutcome`].
//! 3. **[`GatewayInbound::ApplyOutcome`]** (Rust->Python): "persist these validated
//!    effects + write the audit row, then give me the deliveries to publish." Python
//!    applies the effects, commits the game DB then the audit DB, and assembles the
//!    legacy `command_result` + fan-out.
//! 4. **[`GatewayOutbound::OutcomeApplied`]** (Python->Rust): the opaque
//!    `direct_reply` (legacy `command_result` for the actor) plus the
//!    [`DeliveryDirective`]s Rust publishes via the existing [`Self::Deliver`]
//!    fan-out path.
//!
//! **Commit-before-publish is preserved exactly (Decision 5):** Python commits both
//! DBs *before* returning [`GatewayOutbound::OutcomeApplied`], and Rust publishes the
//! deliveries only on receipt — so publication still happens strictly after commit,
//! just as `broadcast_command_effects` guarantees in the pure-Python path. The
//! two-DB non-atomicity is the existing, documented behavior and is unchanged;
//! Phase 5 is where the outbox becomes a Rust-owned durable table.
//!
//! These four frames are **additive**: [`CommandEnvelope`], [`CommandOutcome`],
//! [`ScriptRequest`], and [`DeliveryDirective`] are reused verbatim and unchanged.

use serde::{Deserialize, Serialize};

use crate::envelope::{CommandEnvelope, CommandOutcome};
use crate::ids::{CommandId, PlayerId, SessionId};
use crate::script::ScriptRequest;

/// Why a connection was torn down. Its own internally-tagged enum so the wire
/// shape stays uniform (`{"type": "ClientClose"}`) and is extensible later.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum DisconnectReason {
    /// The client socket closed (an involuntary drop / browser navigation) — the
    /// Python side begins its disconnect-grace/flicker handling.
    ClientClose,
    /// The player deliberately quit (e.g. a `quit` command) — Python skips the
    /// double-teardown path.
    GracefulQuit,
}

/// A frame sent from the Rust gateway to the Python adapter. Internally tagged
/// (`{"type": "RedeemTicket", ...}`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum GatewayInbound {
    /// Ask Python to redeem a single-use player WebSocket ticket.
    RedeemTicket {
        /// The `?ticket=` value extracted from the WS-upgrade query.
        ticket: String,
    },
    /// Ask Python to validate an admin JWT (`?token=`) for the admin channel.
    ValidateAdminToken {
        /// The bearer token extracted from the WS-upgrade query.
        token: String,
    },
    /// A player's connection has been established; Python mints/resumes a session.
    Connected {
        /// The authenticated player.
        player_id: PlayerId,
    },
    /// A player's connection has ended.
    Disconnected {
        /// The player whose connection ended.
        player_id: PlayerId,
        /// Whether this was a socket drop or a graceful quit.
        reason: DisconnectReason,
    },
    /// A forwarded command to execute. Wraps an unmodified [`CommandEnvelope`];
    /// serializes as `{"type": "Command", ...envelope fields}`.
    Command(CommandEnvelope),
    /// Phase 4 step 1 (Rust->Python): ask Python to build the [`ScriptRequest`]
    /// snapshot needed to execute the routed verb (see the Phase 4 execution
    /// round-trip in the module docs). The [`CommandEnvelope`] is nested under
    /// `envelope` (not flattened like [`Self::Command`]) so the reply's
    /// `command_id` can correlate against `envelope.command_id`.
    BuildSnapshot {
        /// The routed command whose snapshot Python should materialize.
        envelope: CommandEnvelope,
    },
    /// Phase 4 step 3 (Rust->Python): hand Python the [`CommandOutcome`] Rust
    /// derived so Python persists the validated effects, writes the audit row, and
    /// commits both DBs, then returns the deliveries to publish. Correlated to the
    /// originating [`Self::BuildSnapshot`] by `command_id` (see the module docs).
    ApplyOutcome {
        /// Correlates this application to the executed command's [`CommandId`].
        command_id: CommandId,
        /// The authoritative outcome (messages + validated `applied_effects`) that
        /// Python must persist. Commit-before-publish is preserved: Python commits
        /// before replying with [`GatewayOutbound::OutcomeApplied`].
        outcome: CommandOutcome,
    },
}

/// A frame sent from the Python adapter back to the Rust gateway. Internally
/// tagged (`{"type": "AuthResult", ...}`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum GatewayOutbound {
    /// The result of a player [`GatewayInbound::RedeemTicket`] handoff. On
    /// rejection, `accepted` is `false` and `player_id` is `None`; Rust closes with
    /// 1008. Admin-token validation uses the shape-distinct [`Self::AdminAuthResult`]
    /// instead (see the resolved admin-push design in the module docs).
    AuthResult {
        /// Whether the credential was accepted.
        accepted: bool,
        /// The authenticated player on acceptance, else `None`.
        player_id: Option<PlayerId>,
    },
    /// The result of a [`GatewayInbound::ValidateAdminToken`] handoff for the
    /// push-only admin console. Deliberately **distinct** from [`Self::AuthResult`]
    /// and carrying no `player_id` — an admin token is not player-scoped, so a
    /// validated admin cannot be routed through the player session path (see the
    /// resolved admin-push design in the module docs). On rejection `accepted` is
    /// `false` and Rust closes with 1008.
    AdminAuthResult {
        /// Whether the admin token was accepted.
        accepted: bool,
    },
    /// Acknowledges a `Connected` handshake with the freshly minted/resumed session
    /// and the frames to replay into the just-connected client.
    ConnectAck {
        /// The session Python minted or resumed for this connection.
        session_id: SessionId,
        /// The room the player is currently in (plain id; no `RoomId` newtype).
        room_id: String,
        /// Opaque legacy frames to deliver directly to the connecting client.
        direct_frames: Vec<serde_json::Value>,
    },
    /// The synchronous reply to a forwarded `Command`, correlated by `command_id`
    /// (see OPEN ITEM 1 resolution in the module docs).
    CommandReply {
        /// Correlates this reply to the originating [`GatewayInbound::Command`].
        command_id: CommandId,
        /// The opaque legacy `command_result` payload for the issuing client.
        direct_reply: serde_json::Value,
        /// Fan-out directives produced as a side effect of the command.
        deliveries: Vec<DeliveryDirective>,
    },
    /// Phase 4 step 2 (Python->Rust): the [`ScriptRequest`] snapshot answering a
    /// [`GatewayInbound::BuildSnapshot`], correlated by `command_id` (= the
    /// originating envelope's [`CommandId`]). Rust executes the migrated feature
    /// against this immutable snapshot and derives a [`CommandOutcome`] (see the
    /// Phase 4 execution round-trip in the module docs).
    SnapshotReady {
        /// Correlates this snapshot to the [`GatewayInbound::BuildSnapshot`] that
        /// requested it (the executing command's [`CommandId`]).
        command_id: CommandId,
        /// The fully-materialized, immutable snapshot to execute against. Boxed to
        /// keep the enum's common variants small; the `Box` is wire-transparent, so
        /// the JSON is identical to an inline [`ScriptRequest`].
        request: Box<ScriptRequest>,
    },
    /// Phase 4 step 4 (Python->Rust): terminal reply to a
    /// [`GatewayInbound::ApplyOutcome`] — Python has committed both DBs, so Rust may
    /// now publish. Correlated by `command_id`. Commit-before-publish is preserved:
    /// this frame is emitted only *after* Python's commits (see the module docs).
    OutcomeApplied {
        /// Correlates this reply to the [`GatewayInbound::ApplyOutcome`] it answers.
        command_id: CommandId,
        /// The opaque legacy `command_result` payload for the issuing client
        /// (relayed verbatim, exactly like `CommandReply`'s `direct_reply`).
        direct_reply: serde_json::Value,
        /// Post-commit fan-out directives Rust publishes via the [`Self::Deliver`]
        /// path. Empty for a zero-broadcast verb.
        deliveries: Vec<DeliveryDirective>,
    },
    /// Phase 4 short-circuit (Python->Rust): **end the execution round-trip early**
    /// and tell Rust to reply to the issuing client with `direct_reply` instead of
    /// continuing. Correlated by `command_id` (= the executing command's
    /// [`CommandId`]), it may answer *either* leg — sent in place of a
    /// [`Self::SnapshotReady`] (before any feature runs) **or** in place of a
    /// [`Self::OutcomeApplied`] (before persistence completes).
    ///
    /// One reusable frame covers both short-circuit cases (see the Phase 4b
    /// hardening notes in the module docs):
    ///
    /// 1. **Frozen-session rejection.** Python's `_on_build_snapshot` finds the
    ///    session `frozen` and rejects *before* executing — no feature, no
    ///    `ApplyOutcome`, no audit, no broadcast — carrying the frozen `system`
    ///    message as `direct_reply` (parity with the pure-Python `handle_ws_command`
    ///    guard).
    /// 2. **Persistence-handler failure.** A `BuildSnapshot`/`ApplyOutcome` handler
    ///    raised (vanished player/room, unknown effect, unknown `command_id`);
    ///    rather than dropping the reply (which would wedge the Rust driver), Python
    ///    logs the traceback and returns this frame with a client-facing in-game
    ///    `error` payload as `direct_reply`.
    ///
    /// It carries **no** `deliveries`: a rejected command publishes nothing. Rust
    /// sends `direct_reply` to the client, runs no further round-trip for this
    /// `command_id`, and cleans up its pending-execution slot.
    ExecutionRejected {
        /// Correlates this rejection to the executing command's [`CommandId`]
        /// (the same key its [`GatewayInbound::BuildSnapshot`]/
        /// [`GatewayInbound::ApplyOutcome`] used).
        command_id: CommandId,
        /// The opaque legacy reply to send the issuing client instead of the
        /// executed result — a frozen `system` message or a degraded `error`
        /// payload (relayed verbatim, exactly like `OutcomeApplied.direct_reply`).
        direct_reply: serde_json::Value,
    },
    /// Phase 4c defer (Python->Rust): **this routed command is not Rust-executable
    /// this phase — run it entirely in Python instead.** Answered in place of a
    /// [`Self::SnapshotReady`] on the [`GatewayInbound::BuildSnapshot`] leg,
    /// correlated by `command_id`.
    ///
    /// Unlike [`Self::ExecutionRejected`] (which *ends* the round-trip with a
    /// terminal client reply), `DeferToPython` tells the Rust driver to fall back to
    /// the ordinary Phase-3 forward path: it re-sends the original
    /// [`CommandEnvelope`] as a [`GatewayInbound::Command`] and returns the
    /// resulting [`Self::CommandReply`] — so Python executes the whole verb (mutation,
    /// audit, broadcast) exactly as an un-migrated command would.
    ///
    /// The motivating case (movement, migration-plan OPEN ITEM #3): a `go <dir>`
    /// whose **target terrain is skill-gated** draws RNG via `SkillService.record_use`.
    /// Cross-language RNG parity is deferred to Phase 5, so the skill-gate + RNG draw
    /// **must stay in Python** this phase. Python's `BuildSnapshot` handler detects a
    /// skill-gated target and returns this frame rather than a snapshot, keeping the
    /// RNG-drawing path entirely Python-side while non-skill-gated moves still execute
    /// in Rust. It carries **no** payload beyond the correlation id — the command is
    /// not being answered, it is being re-routed.
    DeferToPython {
        /// Correlates this defer to the executing command's [`CommandId`] (the same
        /// key its [`GatewayInbound::BuildSnapshot`] used). Rust re-forwards the
        /// original envelope under this id.
        command_id: CommandId,
    },
    /// An unsolicited async push (clock ticks, weather, cross-player deliveries).
    /// Carries no correlation id because it is not a reply to any inbound frame.
    Deliver {
        /// The fan-out directive to relay.
        directive: DeliveryDirective,
    },
    /// A registry state update: a player changed rooms during command handling.
    ///
    /// **Not a delivery** — it carries no payload and fans nothing out. It exists
    /// solely to keep Rust's authoritative `player -> room` / `room -> players`
    /// maps ([`ConnectionRegistry`](crate::gateway) on the events crate) in step
    /// with Python's mid-command `move_player`, so a subsequent
    /// [`DeliveryTarget::Room`] broadcast aimed at the mover's **new** room
    /// actually reaches them. The Rust read loop applies it by calling
    /// `ConnectionRegistry::move_player`.
    ///
    /// Sent **in order ahead of** the moving command's own deliveries down the
    /// same link, so by the time any later room-targeted `Deliver`/`CommandReply`
    /// is resolved, the registry already places the mover in `to_room`. Python
    /// emits it for both command paths (the WS `CommandReply` path folds the
    /// move frames just before the reply; the HTMX `POST /command` push path
    /// flushes them just before its post-command fan-out).
    MovePlayer {
        /// The player who changed rooms.
        player_id: PlayerId,
        /// The room the player left, if known (mirrors Python's truthiness: an
        /// empty/absent origin is treated as "unset" by the registry).
        from_room: Option<String>,
        /// The room the player moved into (plain id; no `RoomId` newtype).
        to_room: String,
    },
    /// Terminal acknowledgement that a [`GatewayInbound::Disconnected`] teardown
    /// finished. It is emitted **after** all of the teardown's fan-out
    /// [`GatewayOutbound::Deliver`] frames (the `player_left` broadcast, the
    /// connection-flicker narration, the `players-online` refresh, and any
    /// follow-break notices), so by the time the Rust read loop sees this frame it
    /// has already dispatched every one of those `Deliver`s into the shared
    /// registry. The Rust gateway awaits this before dropping the dying
    /// per-connection link, which is what guarantees the remaining room siblings
    /// actually receive the leave (see `forward.rs`'s `send_disconnected`). Carries
    /// no correlation id — a link disconnects exactly once.
    DisconnectAck,
}

/// A single fan-out directive: relay an opaque `payload` to a set of recipients.
///
/// Rust resolves `target`/`exclude` against its authoritative connection map and
/// relays `payload` without interpreting it (see the module docs).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DeliveryDirective {
    /// Who should receive the payload.
    pub target: DeliveryTarget,
    /// A player to omit from delivery (e.g. the actor who caused the broadcast).
    pub exclude: Option<PlayerId>,
    /// The opaque legacy frame to relay verbatim. Neither side interprets it.
    pub payload: serde_json::Value,
    /// Optional coalescing key stamped by the **policy owner** (Python) so the
    /// Rust outbound-queue *mechanism* can keep-latest without interpreting the
    /// opaque `payload` (Phase 3c coalescing, design decision 10). Two queued
    /// frames sharing a non-`None` key are idempotent panel refreshes and
    /// collapse to the latest; a `None` key (e.g. `feed_append`) always queues.
    ///
    /// Additive and defaulted to `None`: the field is skipped on serialization
    /// when absent, so every pre-existing frame's wire shape is byte-identical.
    /// Python stamps it in a later task (this task only plumbs + honors it).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub coalesce_key: Option<String>,
}

/// The recipient set for a [`DeliveryDirective`]. Internally tagged
/// (`{"type": "Player", "id": ...}` / `{"type": "Room", "id": ...}` /
/// `{"type": "Global"}` / `{"type": "Admin"}`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum DeliveryTarget {
    /// Deliver to a single player.
    Player {
        /// The recipient player.
        id: PlayerId,
    },
    /// Deliver to everyone in a room (plain room id; no `RoomId` newtype).
    Room {
        /// The room whose occupants receive the payload.
        id: String,
    },
    /// Deliver to every connected player.
    Global,
    /// Deliver to every connected admin console. Resolved against Rust's
    /// admin registry rather than the player registry (see the resolved
    /// admin-push design in the module docs); the opaque `payload` is relayed
    /// unchanged, exactly like [`Self::Room`]/[`Self::Global`] for players.
    Admin,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::effects::Effect;
    use crate::envelope::{Diagnostic, OutcomeStatus};
    use crate::ids::{ActorId, WorldId};
    use crate::messages::OutboundMessage;
    use crate::script::ScriptBudget;
    use crate::snapshot::EntitySnapshot;
    use crate::PROTOCOL_VERSION;
    use serde_json::json;
    use std::collections::BTreeMap;

    fn assert_round_trip<T>(value: &T)
    where
        T: Serialize + for<'de> Deserialize<'de> + PartialEq + std::fmt::Debug,
    {
        let text = serde_json::to_string(value).expect("serialize");
        let back: T = serde_json::from_str(&text).expect("deserialize");
        assert_eq!(*value, back);
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

    fn sample_directive() -> DeliveryDirective {
        DeliveryDirective {
            target: DeliveryTarget::Room {
                id: "tavern".into(),
            },
            exclude: Some(PlayerId("player-1".into())),
            payload: json!({"type": "feed_append", "text": "You go north."}),
            coalesce_key: None,
        }
    }

    /// A non-trivial [`ScriptRequest`] with nested attribute JSON, exercising the
    /// recursive snapshot/budget serialization the `SnapshotReady` frame carries.
    fn sample_script_request() -> ScriptRequest {
        let mut attrs: BTreeMap<String, serde_json::Value> = BTreeMap::new();
        attrs.insert("name".into(), json!("Village Square"));
        attrs.insert("exits".into(), json!(["north", "south"]));
        attrs.insert("nested".into(), json!({"a": [1, 2, {"b": true}]}));
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
                id: "village_square".into(),
                kind: "room".into(),
                attributes: attrs,
            },
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
        }
    }

    /// A non-trivial [`CommandOutcome`] carrying a tagged message + a tagged effect,
    /// exercising the recursive nested-container serialization the `ApplyOutcome`
    /// frame carries.
    fn sample_outcome() -> CommandOutcome {
        CommandOutcome {
            command_id: CommandId("cmd-1".into()),
            status: OutcomeStatus::Executed,
            commit_sequence: Some(3),
            messages: vec![OutboundMessage::Feed {
                text: "You are in the village square.".into(),
                message_type: "system".into(),
            }],
            applied_effects: vec![Effect::MoveEntity {
                entity: "player-1".into(),
                from: "village_square".into(),
                to: "north_road".into(),
            }],
            diagnostics: vec![Diagnostic {
                level: "info".into(),
                message: "ok".into(),
            }],
            room_narration: vec![],
            arrival_narration: vec![],
        }
    }

    #[test]
    fn disconnect_reason_variants_round_trip_and_tag() {
        for (reason, tag) in [
            (DisconnectReason::ClientClose, "ClientClose"),
            (DisconnectReason::GracefulQuit, "GracefulQuit"),
        ] {
            assert_eq!(serde_json::to_value(&reason).unwrap(), json!({"type": tag}));
            assert_round_trip(&reason);
        }
    }

    #[test]
    fn each_gateway_inbound_variant_round_trips_and_tags() {
        let cases: Vec<(GatewayInbound, &str)> = vec![
            (
                GatewayInbound::RedeemTicket {
                    ticket: "tkt-1".into(),
                },
                "RedeemTicket",
            ),
            (
                GatewayInbound::ValidateAdminToken {
                    token: "jwt-1".into(),
                },
                "ValidateAdminToken",
            ),
            (
                GatewayInbound::Connected {
                    player_id: PlayerId("player-1".into()),
                },
                "Connected",
            ),
            (
                GatewayInbound::Disconnected {
                    player_id: PlayerId("player-1".into()),
                    reason: DisconnectReason::ClientClose,
                },
                "Disconnected",
            ),
            (GatewayInbound::Command(sample_envelope()), "Command"),
            (
                GatewayInbound::BuildSnapshot {
                    envelope: sample_envelope(),
                },
                "BuildSnapshot",
            ),
            (
                GatewayInbound::ApplyOutcome {
                    command_id: CommandId("cmd-1".into()),
                    outcome: sample_outcome(),
                },
                "ApplyOutcome",
            ),
        ];
        for (frame, tag) in cases {
            let value = serde_json::to_value(&frame).unwrap();
            assert_eq!(value["type"], json!(tag));
            assert_round_trip(&frame);
        }
    }

    #[test]
    fn command_inbound_flattens_envelope_fields() {
        // The `Command` newtype variant flattens the envelope alongside the tag,
        // reusing the unchanged envelope wire shape.
        let value = serde_json::to_value(GatewayInbound::Command(sample_envelope())).unwrap();
        assert_eq!(value["type"], json!("Command"));
        assert_eq!(value["raw"], json!("look"));
        assert_eq!(value["world_id"], json!("world-1"));
        assert_eq!(value["command_id"], json!("cmd-1"));
    }

    #[test]
    fn disconnected_nests_reason_tag() {
        let value = serde_json::to_value(GatewayInbound::Disconnected {
            player_id: PlayerId("player-1".into()),
            reason: DisconnectReason::GracefulQuit,
        })
        .unwrap();
        assert_eq!(
            value,
            json!({
                "type": "Disconnected",
                "player_id": "player-1",
                "reason": {"type": "GracefulQuit"},
            })
        );
    }

    #[test]
    fn each_gateway_outbound_variant_round_trips_and_tags() {
        let cases: Vec<(GatewayOutbound, &str)> = vec![
            (
                GatewayOutbound::AuthResult {
                    accepted: true,
                    player_id: Some(PlayerId("player-1".into())),
                },
                "AuthResult",
            ),
            (
                GatewayOutbound::AdminAuthResult { accepted: true },
                "AdminAuthResult",
            ),
            (
                GatewayOutbound::ConnectAck {
                    session_id: SessionId("session-1".into()),
                    room_id: "tavern".into(),
                    direct_frames: vec![json!({"type": "state_change"})],
                },
                "ConnectAck",
            ),
            (
                GatewayOutbound::CommandReply {
                    command_id: CommandId("cmd-1".into()),
                    direct_reply: json!({"command": "look", "messages": []}),
                    deliveries: vec![sample_directive()],
                },
                "CommandReply",
            ),
            (
                GatewayOutbound::SnapshotReady {
                    command_id: CommandId("cmd-1".into()),
                    request: Box::new(sample_script_request()),
                },
                "SnapshotReady",
            ),
            (
                GatewayOutbound::OutcomeApplied {
                    command_id: CommandId("cmd-1".into()),
                    direct_reply: json!({"command": "look", "messages": []}),
                    deliveries: vec![sample_directive()],
                },
                "OutcomeApplied",
            ),
            (
                GatewayOutbound::ExecutionRejected {
                    command_id: CommandId("cmd-1".into()),
                    direct_reply: json!({"type": "system", "text": "frozen"}),
                },
                "ExecutionRejected",
            ),
            (
                GatewayOutbound::DeferToPython {
                    command_id: CommandId("cmd-1".into()),
                },
                "DeferToPython",
            ),
            (
                GatewayOutbound::Deliver {
                    directive: sample_directive(),
                },
                "Deliver",
            ),
            (
                GatewayOutbound::MovePlayer {
                    player_id: PlayerId("player-1".into()),
                    from_room: Some("tavern".into()),
                    to_room: "square".into(),
                },
                "MovePlayer",
            ),
            (GatewayOutbound::DisconnectAck, "DisconnectAck"),
        ];
        for (frame, tag) in cases {
            let value = serde_json::to_value(&frame).unwrap();
            assert_eq!(value["type"], json!(tag));
            assert_round_trip(&frame);
        }
    }

    #[test]
    fn disconnect_ack_serializes_as_bare_tag() {
        // The teardown-completion frame carries no fields — just its tag.
        assert_eq!(
            serde_json::to_value(GatewayOutbound::DisconnectAck).unwrap(),
            json!({"type": "DisconnectAck"})
        );
    }

    #[test]
    fn auth_result_reject_serializes_null_player_id() {
        let value = serde_json::to_value(GatewayOutbound::AuthResult {
            accepted: false,
            player_id: None,
        })
        .unwrap();
        assert_eq!(
            value,
            json!({"type": "AuthResult", "accepted": false, "player_id": null})
        );
    }

    #[test]
    fn admin_auth_result_has_no_player_id_field() {
        // The admin auth outcome is shape-distinct from the player `AuthResult`:
        // it carries only `accepted`, so a validated admin can never be mistaken
        // for a player (see the resolved admin-push design in the module docs).
        let accept =
            serde_json::to_value(GatewayOutbound::AdminAuthResult { accepted: true }).unwrap();
        assert_eq!(accept, json!({"type": "AdminAuthResult", "accepted": true}));
        let reject =
            serde_json::to_value(GatewayOutbound::AdminAuthResult { accepted: false }).unwrap();
        assert_eq!(
            reject,
            json!({"type": "AdminAuthResult", "accepted": false})
        );
        assert!(accept.get("player_id").is_none());
        assert_round_trip(&GatewayOutbound::AdminAuthResult { accepted: true });
    }

    #[test]
    fn command_reply_carries_correlation_id() {
        // OPEN ITEM 1: the reply is correlated to its command by `command_id`.
        let value = serde_json::to_value(GatewayOutbound::CommandReply {
            command_id: CommandId("cmd-42".into()),
            direct_reply: json!({"ok": true}),
            deliveries: vec![],
        })
        .unwrap();
        assert_eq!(value["type"], json!("CommandReply"));
        assert_eq!(value["command_id"], json!("cmd-42"));
        assert_eq!(value["deliveries"], json!([]));
    }

    #[test]
    fn move_player_frame_shape_and_optional_from_room() {
        // A move with a known origin serializes both rooms alongside the tag.
        let with_origin = GatewayOutbound::MovePlayer {
            player_id: PlayerId("player-1".into()),
            from_room: Some("tavern".into()),
            to_room: "square".into(),
        };
        assert_eq!(
            serde_json::to_value(&with_origin).unwrap(),
            json!({
                "type": "MovePlayer",
                "player_id": "player-1",
                "from_room": "tavern",
                "to_room": "square",
            })
        );
        assert_round_trip(&with_origin);

        // An unknown origin serializes `from_room` as null (mirrors Python's
        // `Optional[str]` -> `None`); the registry treats it as "unset".
        let no_origin = GatewayOutbound::MovePlayer {
            player_id: PlayerId("player-1".into()),
            from_room: None,
            to_room: "square".into(),
        };
        let value = serde_json::to_value(&no_origin).unwrap();
        assert_eq!(value["from_room"], json!(null));
        assert_round_trip(&no_origin);
    }

    #[test]
    fn each_delivery_target_variant_round_trips_and_tags() {
        let cases: Vec<(DeliveryTarget, serde_json::Value)> = vec![
            (
                DeliveryTarget::Player {
                    id: PlayerId("player-1".into()),
                },
                json!({"type": "Player", "id": "player-1"}),
            ),
            (
                DeliveryTarget::Room {
                    id: "tavern".into(),
                },
                json!({"type": "Room", "id": "tavern"}),
            ),
            (DeliveryTarget::Global, json!({"type": "Global"})),
            (DeliveryTarget::Admin, json!({"type": "Admin"})),
        ];
        for (target, shape) in cases {
            assert_eq!(serde_json::to_value(&target).unwrap(), shape);
            assert_round_trip(&target);
        }
    }

    #[test]
    fn delivery_directive_round_trips_and_keeps_payload_opaque() {
        let directive = sample_directive();
        let value = serde_json::to_value(&directive).unwrap();
        // Payload is relayed verbatim, not reinterpreted.
        assert_eq!(value["payload"]["type"], json!("feed_append"));
        assert_eq!(value["exclude"], json!("player-1"));
        assert_round_trip(&directive);
    }

    #[test]
    fn coalesce_key_defaults_none_and_is_absent_on_the_wire() {
        // An unset `coalesce_key` must not appear in the serialized frame so every
        // pre-existing directive is byte-identical to before the field was added.
        let directive = sample_directive();
        assert_eq!(directive.coalesce_key, None);
        let value = serde_json::to_value(&directive).unwrap();
        assert!(
            value.get("coalesce_key").is_none(),
            "absent key must be skipped, not serialized as null"
        );
        // A frame produced *without* the field must still deserialize (default None).
        let legacy = json!({
            "target": {"type": "Global"},
            "exclude": null,
            "payload": {"type": "clock_tick"},
        });
        let back: DeliveryDirective = serde_json::from_value(legacy).unwrap();
        assert_eq!(back.coalesce_key, None);
    }

    #[test]
    fn build_snapshot_nests_envelope_under_field_not_flattened() {
        // Unlike the `Command` newtype variant (which flattens the envelope beside
        // the tag), `BuildSnapshot` nests it under `envelope` so the reply's
        // `command_id` can correlate against `envelope.command_id`.
        let frame = GatewayInbound::BuildSnapshot {
            envelope: sample_envelope(),
        };
        let value = serde_json::to_value(&frame).unwrap();
        assert_eq!(value["type"], json!("BuildSnapshot"));
        assert_eq!(value["envelope"]["command_id"], json!("cmd-1"));
        assert_eq!(value["envelope"]["raw"], json!("look"));
        // The envelope must NOT be flattened alongside the tag.
        assert!(value.get("raw").is_none());
        assert_round_trip(&frame);
    }

    #[test]
    fn apply_outcome_round_trips_full_nested_outcome() {
        // The `outcome`'s tagged message + tagged effect must survive the round trip
        // through the recursive container serialization (not flattened away).
        let frame = GatewayInbound::ApplyOutcome {
            command_id: CommandId("cmd-1".into()),
            outcome: sample_outcome(),
        };
        let value = serde_json::to_value(&frame).unwrap();
        assert_eq!(value["type"], json!("ApplyOutcome"));
        assert_eq!(value["command_id"], json!("cmd-1"));
        assert_eq!(value["outcome"]["status"], json!("Executed"));
        assert_eq!(value["outcome"]["messages"][0]["type"], json!("Feed"));
        assert_eq!(
            value["outcome"]["applied_effects"][0]["type"],
            json!("MoveEntity")
        );
        assert_round_trip(&frame);
    }

    #[test]
    fn snapshot_ready_round_trips_full_nested_request() {
        // The nested `ScriptRequest`'s recursive snapshot attributes must survive.
        let frame = GatewayOutbound::SnapshotReady {
            command_id: CommandId("cmd-1".into()),
            request: Box::new(sample_script_request()),
        };
        let value = serde_json::to_value(&frame).unwrap();
        assert_eq!(value["type"], json!("SnapshotReady"));
        assert_eq!(value["command_id"], json!("cmd-1"));
        assert_eq!(value["request"]["script_id"], json!("look"));
        assert_eq!(
            value["request"]["room_snapshot"]["attributes"]["nested"]["a"][2]["b"],
            json!(true)
        );
        assert_round_trip(&frame);
    }

    #[test]
    fn outcome_applied_carries_correlation_and_opaque_reply() {
        // `direct_reply` is relayed opaquely; `deliveries` round-trip verbatim.
        let frame = GatewayOutbound::OutcomeApplied {
            command_id: CommandId("cmd-42".into()),
            direct_reply: json!({"command": "look", "ok": true}),
            deliveries: vec![sample_directive()],
        };
        let value = serde_json::to_value(&frame).unwrap();
        assert_eq!(value["type"], json!("OutcomeApplied"));
        assert_eq!(value["command_id"], json!("cmd-42"));
        assert_eq!(value["direct_reply"]["command"], json!("look"));
        assert_eq!(
            value["deliveries"][0]["payload"]["type"],
            json!("feed_append")
        );
        assert_round_trip(&frame);

        // A zero-broadcast verb (e.g. a private `look`) has empty deliveries.
        let empty = GatewayOutbound::OutcomeApplied {
            command_id: CommandId("cmd-42".into()),
            direct_reply: json!({"ok": true}),
            deliveries: vec![],
        };
        assert_eq!(
            serde_json::to_value(&empty).unwrap()["deliveries"],
            json!([])
        );
        assert_round_trip(&empty);
    }

    #[test]
    fn execution_rejected_carries_correlation_and_opaque_reply_no_deliveries() {
        // The short-circuit frame (frozen rejection / persistence failure) is
        // correlated by `command_id`, relays `direct_reply` opaquely, and carries
        // no deliveries field at all — a rejected command publishes nothing.
        let frame = GatewayOutbound::ExecutionRejected {
            command_id: CommandId("cmd-7".into()),
            direct_reply: json!({
                "type": "system",
                "text": "Your session is frozen. Contact an administrator.",
            }),
        };
        let value = serde_json::to_value(&frame).unwrap();
        assert_eq!(value["type"], json!("ExecutionRejected"));
        assert_eq!(value["command_id"], json!("cmd-7"));
        assert_eq!(value["direct_reply"]["type"], json!("system"));
        assert!(
            value.get("deliveries").is_none(),
            "a rejection carries no deliveries"
        );
        assert_round_trip(&frame);

        // The persistence-failure shape (an `error` payload) round-trips too.
        let err_frame = GatewayOutbound::ExecutionRejected {
            command_id: CommandId("cmd-8".into()),
            direct_reply: json!({"type": "error", "message": "logged for review."}),
        };
        assert_eq!(
            serde_json::to_value(&err_frame).unwrap()["direct_reply"]["type"],
            json!("error")
        );
        assert_round_trip(&err_frame);
    }

    #[test]
    fn defer_to_python_carries_only_correlation_id() {
        // The 4c defer frame carries just its tag + correlation id — no reply, no
        // deliveries: the command is being re-routed to Python, not answered.
        let frame = GatewayOutbound::DeferToPython {
            command_id: CommandId("cmd-skill".into()),
        };
        let value = serde_json::to_value(&frame).unwrap();
        assert_eq!(
            value,
            json!({"type": "DeferToPython", "command_id": "cmd-skill"})
        );
        assert!(value.get("direct_reply").is_none());
        assert!(value.get("deliveries").is_none());
        assert_round_trip(&frame);
    }

    #[test]
    fn coalesce_key_present_round_trips_and_is_serialized() {
        // When the policy owner stamps a key it survives the round trip verbatim.
        let directive = DeliveryDirective {
            target: DeliveryTarget::Player {
                id: PlayerId("player-1".into()),
            },
            exclude: None,
            payload: json!({"type": "state_change", "panel": "inventory"}),
            coalesce_key: Some("panel:inventory".into()),
        };
        let value = serde_json::to_value(&directive).unwrap();
        assert_eq!(value["coalesce_key"], json!("panel:inventory"));
        assert_round_trip(&directive);
    }
}
