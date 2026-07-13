//! `auth.rs` — the transport-side of the auth handoff (Phase 3b/3c stub).
//!
//! Per design decision 6, **Rust owns transport, Python owns credential/session
//! policy**: Rust extracts `?ticket=` (player) or `?token=` (admin) from the WS
//! upgrade query and forwards it to the Python adapter
//! ([`GatewayInbound::RedeemTicket`](lorecraft_protocol::gateway::GatewayInbound)
//! / `ValidateAdminToken`), which returns an
//! [`AuthResult`](lorecraft_protocol::gateway::GatewayOutbound). Rust never sees
//! the JWT secret.
//!
//! This module is an intentional 3a **stub** establishing the file layout decision
//! 9 specifies: the real handoff (which correlates an `AuthResult` frame back to a
//! pending redemption) is filled in when the sockets go live — player ticket auth
//! in Phase 3b, admin token auth in Phase 3c — so those diffs are additive here.

use lorecraft_protocol::ids::PlayerId;

use crate::forward::ForwardClient;

/// Why an auth handoff was rejected.
#[derive(Debug, thiserror::Error)]
pub enum AuthError {
    /// Python rejected the credential (bad/expired ticket or invalid admin token);
    /// the caller closes the socket with WS 1008.
    #[error("credential rejected")]
    Rejected,
    /// The handoff to Python failed at the transport level.
    #[error("auth handoff transport error")]
    Transport,
}

/// Redeem a single-use player WS `?ticket=` via the Python adapter, resolving the
/// authenticated [`PlayerId`] on success.
///
/// Phase 3b fills this in: forward a `RedeemTicket` and await the correlated
/// `AuthResult`. Stubbed in 3a because 3a performs no live cutover.
pub async fn redeem_player_ticket(
    _forward: &ForwardClient,
    _ticket: &str,
) -> Result<PlayerId, AuthError> {
    todo!("player ticket redemption handoff is wired in Phase 3b")
}

/// Validate an admin `?token=` JWT via the Python adapter.
///
/// Phase 3c fills this in, preserving the admin **accept-before-validate** nuance
/// (accept the upgrade, then close 1008 on reject) so the admin UI's 1008-vs-1006
/// distinction survives. Stubbed in 3a.
pub async fn validate_admin_token(_forward: &ForwardClient, _token: &str) -> Result<(), AuthError> {
    todo!("admin token validation handoff is wired in Phase 3c")
}
