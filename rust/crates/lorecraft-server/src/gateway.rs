//! `gateway.rs` — the Axum app skeleton: config, shared state, and router.
//!
//! It boots an Axum [`Router`] with a real `GET /healthz` route, the **live**
//! player `/ws` route ([`crate::ws_player`], Phase 3b), and the **live** admin
//! `/admin/ws` route ([`crate::ws_admin`], Phase 3c), sharing a [`GatewayState`]
//! that threads the static [`GatewayConfig`], the authoritative
//! [`ConnectionRegistry`], the slow-client [`DisconnectHub`], and the shared
//! [`ForwardClient`] into every handler. (Each player/admin WS handler opens its
//! own per-connection `ForwardClient`; the shared one serves the health check —
//! see `forward.rs`'s module docs for the per-connection-link design decision.)
//!
//! Config is **static** this phase (design decision 12): the dials here
//! (bind address, socket path, world id, deadline, queue depth) are *operational*,
//! not game-balance, so they do not use the live-tunable `WorldClock` pattern.

use std::collections::HashSet;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use axum::extract::State;
use axum::routing::get;
use axum::{Json, Router};
use lorecraft_events::{
    BackpressureConfig, ConnectionRegistry, RateLimitConfig, DEFAULT_OUTBOUND_QUEUE_DEPTH,
};
use serde_json::json;

use crate::disconnect::{DisconnectHub, DispatchContext};
use crate::forward::ForwardClient;
use crate::{proxy, ws_admin, ws_player};

/// Static gateway configuration (design decision 12 — operational, not
/// game-balance, so static config this phase rather than a live-tunable singleton).
#[derive(Debug, Clone)]
pub struct GatewayConfig {
    /// Address the Axum HTTP/WS server binds.
    pub bind_address: SocketAddr,
    /// Filesystem path of the Python adapter's UDS listener.
    pub socket_path: PathBuf,
    /// The single world id stamped onto forwarded command envelopes (decision 3).
    pub world_id: String,
    /// Base URL of the Python uvicorn backend that all non-`/ws`/`/healthz`
    /// requests are reverse-proxied to (Phase 3b, Option A). No trailing slash is
    /// required — the proxy trims one if present. Plain HTTP loopback origin.
    pub backend_url: String,
    /// Default per-command execution budget stamped onto envelopes.
    pub default_deadline_ms: u64,
    /// Depth of each connection's bounded outbound queue.
    pub outbound_queue_depth: usize,
    /// Timeout applied to each connect-time handshake step
    /// (`RedeemTicket → AuthResult`, `Connected → ConnectAck`). Required because
    /// the Python adapter acks nothing for an unknown player this phase, so an
    /// un-timed await could hang the upgrade task forever.
    pub handshake_timeout_ms: u64,
    /// Backstop timeout for the disconnect teardown handshake
    /// (`Disconnected → …Deliver… → DisconnectAck`). Bounds how long teardown
    /// waits for Python to emit the leave fan-out + terminal ack, so a slow or
    /// misbehaving adapter can never wedge a connection's teardown forever; on
    /// expiry the link is dropped anyway (logged).
    pub disconnect_timeout_ms: u64,
    /// Backstop timeout for one Rust-executed command's whole Option-A round-trip
    /// (`BuildSnapshot → SnapshotReady`, feature, `ApplyOutcome → OutcomeApplied`).
    /// Required (Phase 4b) because a Python persistence peer that answers *nothing*
    /// on either leg would otherwise wedge the receive loop forever; on expiry the
    /// pending execution slot is cleaned up, the command surfaces an in-game error
    /// to the client, and the connection stays usable (see [`crate::ws_player`]).
    /// Operational, not game-balance (design decision 12) — static this phase.
    pub execute_timeout_ms: u64,
    /// Slow-client backpressure threshold (Phase 3c, item 3): how many consecutive
    /// outbound-queue overflows a connection may accumulate before the gateway
    /// closes it with WS 1013. Operational, not game-balance (design decision 12) —
    /// static this phase, an ops live-tunable candidate later.
    pub backpressure: BackpressureConfig,
    /// Per-player command rate limit (Phase 3c, item 5): a generous-by-default
    /// token bucket applied to command intake so an abusive flood is throttled while
    /// a well-behaved interactive client never approaches the limit. Operational
    /// config, static this phase.
    pub rate_limit: RateLimitConfig,
    /// Phase 4 verb allow-list: the normalized verbs whose command pipeline Rust
    /// owns (executes via [`crate::execute`]) rather than forwarding to Python.
    ///
    /// **Defaults empty**, so with no configuration every command routes to Python
    /// — byte-identical to the pure Phase 3 path (decision 3). Populated from
    /// `LORECRAFT_RUST_VERBS` (comma-separated) at the binary; enabling a verb is
    /// an operational config change and emptying the list is the rollback. Only a
    /// verb that is *both* migrated and listed here is Rust-executed (see
    /// [`crate::route::decide`]).
    pub rust_verbs: HashSet<String>,
}

impl Default for GatewayConfig {
    fn default() -> Self {
        Self {
            bind_address: SocketAddr::from(([127, 0, 0, 1], 8090)),
            socket_path: PathBuf::from("var/gateway.sock"),
            world_id: "world-1".to_string(),
            backend_url: "http://127.0.0.1:8000".to_string(),
            default_deadline_ms: 5_000,
            outbound_queue_depth: DEFAULT_OUTBOUND_QUEUE_DEPTH,
            handshake_timeout_ms: 5_000,
            disconnect_timeout_ms: 5_000,
            execute_timeout_ms: 5_000,
            backpressure: BackpressureConfig::default(),
            rate_limit: RateLimitConfig::default(),
            // Empty == pure Phase 3 rollback: no verb is Rust-executed by default.
            rust_verbs: HashSet::new(),
        }
    }
}

/// Shared, cheaply-cloneable application state handed to every route handler.
///
/// All fields are `Arc`, so cloning per request is a refcount bump. The player
/// (3b) and admin (3c) WS handlers consume `registry` + `forward` + `config`; the
/// 3a health check already reads all three so the wiring is exercised for real.
#[derive(Clone)]
pub struct GatewayState {
    /// Static configuration.
    pub config: Arc<GatewayConfig>,
    /// The authoritative connection/room map (fan-out source of truth).
    pub registry: Arc<ConnectionRegistry>,
    /// The framed UDS client forwarding commands to the Python adapter.
    pub forward: Arc<ForwardClient>,
    /// The server-owned slow-client close-signal hub (Phase 3c, item 3): shared by
    /// every per-connection `ForwardClient` so a dispatch-detected overflow on any
    /// link can close the stalled connection's socket.
    pub disconnect: Arc<DisconnectHub>,
    /// Shared HTTP client used by the reverse proxy to reach the Python backend
    /// (redirect-following disabled; see [`crate::proxy`]).
    pub http_client: Arc<reqwest::Client>,
}

impl GatewayState {
    /// Build the [`DispatchContext`] a fresh per-connection `ForwardClient` needs:
    /// the shared registry + close-signal hub + operational backpressure threshold.
    pub fn dispatch_context(&self) -> DispatchContext {
        DispatchContext::new(
            Arc::clone(&self.registry),
            Arc::clone(&self.disconnect),
            self.config.backpressure,
        )
    }
}

/// Build the Axum [`Router`] for the gateway: the health check, the live player
/// (`/ws`) and admin (`/admin/ws`) WS routes, and the reverse-proxy fallback.
pub fn build_router(
    config: Arc<GatewayConfig>,
    registry: Arc<ConnectionRegistry>,
    forward: Arc<ForwardClient>,
    disconnect: Arc<DisconnectHub>,
) -> Router {
    let state = GatewayState {
        config,
        registry,
        forward,
        disconnect,
        http_client: Arc::new(proxy::build_http_client()),
    };
    Router::new()
        .route("/healthz", get(healthz))
        .route("/ws", get(ws_player::upgrade))
        .route("/admin/ws", get(ws_admin::upgrade))
        // Everything else (lobby/login HTML, static assets, /auth/ws-ticket,
        // /command HTMX partials, …) is reverse-proxied to the Python backend.
        // The three routes above keep precedence over this catch-all.
        .fallback(proxy::proxy_handler)
        .with_state(state)
}

/// Liveness/health endpoint. Reports the configured world, the current connected
/// player count (from the registry), and whether the Python forwarding link is up
/// (from the forward client) — proving the whole app-state graph is wired.
async fn healthz(State(state): State<GatewayState>) -> Json<serde_json::Value> {
    Json(json!({
        "status": "ok",
        "world_id": state.config.world_id,
        "connected_players": state.registry.connected_player_ids().len(),
        "gateway_link": if state.forward.is_active() { "up" } else { "down" },
    }))
}
