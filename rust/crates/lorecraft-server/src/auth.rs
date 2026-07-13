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
//! Player ticket redemption ([`redeem_player_ticket`]) is live as of Phase 3b;
//! admin token validation remains a 3c stub.

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
/// Forwards a `RedeemTicket` on the (per-connection) `forward` link and maps the
/// routed `AuthResult`:
///
/// - accepted **with** a player id → `Ok(PlayerId)`;
/// - rejected, or accepted without a player id (a malformed/adminesque result
///   that cannot authenticate a *player* socket) → [`AuthError::Rejected`];
/// - any transport failure → [`AuthError::Transport`].
pub async fn redeem_player_ticket(
    forward: &ForwardClient,
    ticket: &str,
) -> Result<PlayerId, AuthError> {
    match forward.redeem_ticket(ticket).await {
        Ok(decision) if decision.accepted => decision.player_id.ok_or(AuthError::Rejected),
        Ok(_) => Err(AuthError::Rejected),
        Err(err) => {
            tracing::warn!(error = %err, "ticket redemption handoff failed at transport level");
            Err(AuthError::Transport)
        }
    }
}

/// Validate an admin `?token=` JWT via the Python adapter.
///
/// Phase 3c fills this in, preserving the admin **accept-before-validate** nuance
/// (accept the upgrade, then close 1008 on reject) so the admin UI's 1008-vs-1006
/// distinction survives. Stubbed in 3a.
pub async fn validate_admin_token(_forward: &ForwardClient, _token: &str) -> Result<(), AuthError> {
    todo!("admin token validation handoff is wired in Phase 3c")
}
