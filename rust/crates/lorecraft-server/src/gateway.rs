//! `gateway.rs` — the Axum app skeleton: config, shared state, and router.
//!
//! This is the "app skeleton" the 3a checklist asks for. It boots an Axum
//! [`Router`] with a real `GET /healthz` route and the (stubbed) player/admin WS
//! route seams, sharing a [`GatewayState`] that threads the static
//! [`GatewayConfig`], the authoritative [`ConnectionRegistry`], and the
//! [`ForwardClient`] into every handler. The live `/ws`/`/admin/ws` upgrades are
//! filled in by [`crate::ws_player`] (3b) and [`crate::ws_admin`] (3c) — 3a serves
//! no real clients (design spec: "routes not yet serving real clients").
//!
//! Config is **static** this phase (design decision 12): the dials here
//! (bind address, socket path, world id, deadline, queue depth) are *operational*,
//! not game-balance, so they do not use the live-tunable `WorldClock` pattern.

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use axum::extract::State;
use axum::routing::get;
use axum::{Json, Router};
use lorecraft_events::{ConnectionRegistry, DEFAULT_OUTBOUND_QUEUE_DEPTH};
use serde_json::json;

use crate::forward::ForwardClient;
use crate::{ws_admin, ws_player};

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
    /// Default per-command execution budget stamped onto envelopes.
    pub default_deadline_ms: u64,
    /// Depth of each connection's bounded outbound queue.
    pub outbound_queue_depth: usize,
}

impl Default for GatewayConfig {
    fn default() -> Self {
        Self {
            bind_address: SocketAddr::from(([127, 0, 0, 1], 8090)),
            socket_path: PathBuf::from("var/gateway.sock"),
            world_id: "world-1".to_string(),
            default_deadline_ms: 5_000,
            outbound_queue_depth: DEFAULT_OUTBOUND_QUEUE_DEPTH,
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
}

/// Build the Axum [`Router`] for the gateway with the health check wired for real
/// and the player/admin WS route seams in place (stubbed until 3b/3c).
pub fn build_router(
    config: Arc<GatewayConfig>,
    registry: Arc<ConnectionRegistry>,
    forward: Arc<ForwardClient>,
) -> Router {
    let state = GatewayState {
        config,
        registry,
        forward,
    };
    Router::new()
        .route("/healthz", get(healthz))
        .route("/ws", get(ws_player::upgrade))
        .route("/admin/ws", get(ws_admin::upgrade))
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
