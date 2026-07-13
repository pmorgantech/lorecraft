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

use serde::{Deserialize, Serialize};

use crate::envelope::CommandEnvelope;
use crate::ids::{CommandId, PlayerId, SessionId};

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
    /// An unsolicited async push (clock ticks, weather, cross-player deliveries).
    /// Carries no correlation id because it is not a reply to any inbound frame.
    Deliver {
        /// The fan-out directive to relay.
        directive: DeliveryDirective,
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
    use crate::ids::{ActorId, WorldId};
    use crate::PROTOCOL_VERSION;
    use serde_json::json;

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
                GatewayOutbound::Deliver {
                    directive: sample_directive(),
                },
                "Deliver",
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
}
