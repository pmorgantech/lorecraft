//! `ws_admin.rs` — Axum admin `/admin/ws` ingress (Phase 3c stub).
//!
//! Phase 3c fills this in: **accept-before-validate** (accept the upgrade, then
//! close 1008 on a Python token reject so the admin UI's 1008-vs-1006 distinction
//! survives), the `?token=` →
//! [`validate_admin_token`](crate::auth::validate_admin_token) handoff, and the
//! push-only outbound queue drained via `lorecraft-events`. It is a stub in 3a —
//! the design spec sequences the admin cutover last — so only the file and route
//! seam exist now, keeping 3c's diff additive.

use axum::extract::ws::WebSocketUpgrade;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};

/// Handle an admin `/admin/ws` upgrade request.
///
/// Stubbed in 3a: it accepts the `WebSocketUpgrade` extractor but returns `501 Not
/// Implemented` rather than upgrading, since the live admin-socket cutover is Phase
/// 3c. Wiring the real accept-before-validate upgrade is an additive edit here.
pub async fn upgrade(_ws: WebSocketUpgrade) -> Response {
    (
        StatusCode::NOT_IMPLEMENTED,
        "admin /admin/ws upgrade is wired in Phase 3c",
    )
        .into_response()
}
