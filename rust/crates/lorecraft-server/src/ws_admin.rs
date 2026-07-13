//! `ws_admin.rs` — the live Axum admin `/admin/ws` ingress (Phase 3c cutover).
//!
//! This is the Rust cutover of Python's `admin_ws_endpoint`
//! (`src/lorecraft/webui/admin/websocket.py`, the behavior reference). It mirrors
//! the player handler's structure ([`crate::ws_player`]) but is **push-only** and
//! **admin-flavored** — there is no player session, no command intake, and no
//! Python-side admin lifecycle (admin connections are Rust-local; see the resolved
//! admin-push design in `lorecraft-protocol::gateway`). Per connection:
//!
//! 1. **Accept-before-validate** (design decision 6). The upgrade is accepted
//!    *first* (via [`WebSocketUpgrade::on_upgrade`]), then the `?token=` is
//!    validated on the socket task. So a bad/expired token yields an
//!    **application-level 1008** close the admin UI can act on — it distinguishes a
//!    stale-session logout (1008 → force logout) from a transient transport drop
//!    (1006 → reconnect). Closing *before* accept would surface only 1006. This is
//!    the exact nuance Python's `accept()`-then-`close(1008)` preserves.
//! 2. **Token handoff.** A dedicated per-connection [`ForwardClient`] forwards the
//!    token as `ValidateAdminToken`; Python replies with the shape-distinct
//!    `AdminAuthResult { accepted }`. Reject → close **1008**; transport fault →
//!    close 1011.
//! 3. **Registration.** A validated admin's bounded outbound queue is registered in
//!    the Rust-local admin registry ([`ConnectionRegistry::register_admin`]),
//!    yielding an [`AdminId`]. Its slow-client close signal is registered in the
//!    shared [`DisconnectHub`](crate::disconnect::DisconnectHub) exactly like a
//!    player's, so admin consoles get the same backpressure treatment.
//! 4. **Push-only writer.** One writer task drains the queue to the WS sink (with
//!    coalescing + the 1013 slow-client close — see [`crate::writer`]). Admin pushes
//!    reach this connection because Python (a later task) sends
//!    `Deliver { target: Admin, payload }` frames down an admin link; *any*
//!    `ForwardClient` read loop dispatches those to every registered admin.
//! 5. **No-op receive drain.** The receive loop reads and **discards** inbound
//!    frames (Python's admin socket reads subscribe commands that are no-ops today)
//!    purely to detect a client close — it never forwards them as commands.
//! 6. **Teardown.** On socket close / the slow-client signal: deregister the admin
//!    and its close signal, drop the queue, drain the writer, and drop the forward
//!    link.

use axum::extract::ws::{close_code, CloseFrame, Message, Utf8Bytes, WebSocket, WebSocketUpgrade};
use axum::extract::{Query, State};
use axum::response::Response;
use futures_util::StreamExt;
use lorecraft_events::outbound_channel;
use serde::Deserialize;
use tokio::time::{timeout, Duration};

use crate::auth::{self, AuthError};
use crate::disconnect::admin_recipient;
use crate::forward::ForwardClient;
use crate::gateway::GatewayState;
use crate::writer::writer_task;

/// The `/admin/ws` upgrade query. Mirrors Python's `?token=` (defaulting to empty,
/// which Python's `decode_token("")` rejects → 1008).
#[derive(Debug, Deserialize)]
pub struct AdminWsQuery {
    /// The admin bearer JWT extracted from the WS-upgrade query.
    #[serde(default)]
    token: Option<String>,
}

/// Handle an admin `/admin/ws` upgrade request.
///
/// Always accepts the upgrade and runs token validation on the socket task, so a
/// bad token yields an application-level WS **1008** close (distinguishable from a
/// 1006 transport drop) — the accept-before-validate contract the admin UI relies
/// on (see the module docs).
pub async fn upgrade(
    ws: WebSocketUpgrade,
    Query(query): Query<AdminWsQuery>,
    State(state): State<GatewayState>,
) -> Response {
    ws.on_upgrade(move |socket| handle_socket(socket, state, query.token))
}

/// Close the socket with an application-level close frame; best-effort.
async fn close_with(mut socket: WebSocket, code: u16, reason: &str) {
    let frame = CloseFrame {
        code,
        reason: Utf8Bytes::from(reason.to_owned()),
    };
    if let Err(err) = socket.send(Message::Close(Some(frame))).await {
        tracing::debug!(error = %err, code, "admin close frame not delivered");
    }
}

/// The full push-only admin lifecycle (steps 1–6 in the module docs).
async fn handle_socket(socket: WebSocket, state: GatewayState, token: Option<String>) {
    let handshake_budget = Duration::from_millis(state.config.handshake_timeout_ms);

    // 1/2. Dedicated per-connection UDS link, then token validation. The upgrade is
    //      already accepted (on_upgrade), so every rejection below is an
    //      application-level close the admin UI can distinguish from 1006.
    let forward =
        match ForwardClient::connect(&state.config.socket_path, state.dispatch_context()).await {
            Ok(client) => client,
            Err(err) => {
                tracing::warn!(error = %err, "gateway backend unavailable for admin connection");
                close_with(socket, close_code::ERROR, "gateway backend unavailable").await;
                return;
            }
        };

    // An absent/empty token is validated the same way (Python rejects `""`).
    let token = token.unwrap_or_default();
    match timeout(
        handshake_budget,
        auth::validate_admin_token(&forward, &token),
    )
    .await
    {
        Ok(Ok(())) => {}
        Ok(Err(AuthError::Rejected)) => {
            close_with(socket, close_code::POLICY, "Invalid or missing token").await;
            return;
        }
        Ok(Err(AuthError::Transport)) | Err(_) => {
            close_with(socket, close_code::ERROR, "admin auth handoff failed").await;
            return;
        }
    }

    // 3. Register the validated admin + its slow-client close signal.
    let (outbound_tx, outbound_rx) = outbound_channel(state.config.outbound_queue_depth);
    let admin_id = state.registry.register_admin(outbound_tx.clone());
    let recipient = admin_recipient(admin_id);
    let mut close_rx = state.disconnect.register(&recipient);

    // 4. Push-only writer task owns the sink and drains the (coalescing) queue,
    //    closing with 1013 if the slow-client signal fires.
    let (sink, mut stream) = socket.split();
    let writer = tokio::spawn(writer_task(
        sink,
        outbound_rx,
        close_rx.clone(),
        state.config.outbound_queue_depth,
    ));

    // 5. No-op receive drain: read + discard inbound frames only to detect a client
    //    close (or the slow-client signal); never forward them as commands.
    loop {
        tokio::select! {
            biased;
            res = close_rx.changed() => {
                if res.is_ok() && *close_rx.borrow_and_update() {
                    tracing::info!(admin_id = admin_id.0, "slow-consumer admin disconnect; tearing down");
                }
                break;
            }
            maybe = stream.next() => match maybe {
                Some(Ok(Message::Close(_))) | None => break,
                Some(Ok(_)) => {} // subscribe/ping/other frames are no-ops
                Some(Err(err)) => {
                    tracing::debug!(error = %err, admin_id = admin_id.0, "admin receive error");
                    break;
                }
            },
        }
    }

    // 6. Teardown: deregister (no Python-side admin lifecycle to notify), drop the
    //    queue so the writer drains + exits, then drop the forward link.
    state.registry.deregister_admin(admin_id);
    state.disconnect.deregister(&recipient);
    drop(outbound_tx);
    if let Err(err) = writer.await {
        tracing::debug!(error = %err, admin_id = admin_id.0, "admin writer task join error");
    }
    drop(forward);
}
