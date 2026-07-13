//! `ws_player.rs` — Axum player `/ws` ingress (Phase 3b stub).
//!
//! Phase 3b fills this in: the `?ticket=` extraction →
//! [`redeem_player_ticket`](crate::auth::redeem_player_ticket) handoff, the
//! single-live-connection-per-player rule, and the receive loop that forwards each
//! frame as a [`GatewayInbound::Command`](lorecraft_protocol::gateway::GatewayInbound)
//! and relays the `direct_reply` back to the client. It is a stub in 3a — the
//! design spec is explicit that 3a has "no live cutover" — so only the file and
//! route seam exist now, keeping 3b's diff additive.

use axum::extract::ws::WebSocketUpgrade;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};

/// Handle a player `/ws` upgrade request.
///
/// Stubbed in 3a: it accepts the `WebSocketUpgrade` extractor (proving the `ws`
/// feature is wired) but returns `501 Not Implemented` instead of upgrading, since
/// the live player-socket cutover is Phase 3b. Wiring the real upgrade here is an
/// additive edit to this same function.
pub async fn upgrade(_ws: WebSocketUpgrade) -> Response {
    (
        StatusCode::NOT_IMPLEMENTED,
        "player /ws upgrade is wired in Phase 3b",
    )
        .into_response()
}
