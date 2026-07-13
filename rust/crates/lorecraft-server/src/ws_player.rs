//! `ws_player.rs` — the live Axum player `/ws` ingress (Phase 3b).
//!
//! This is the Rust cutover of the Python `/ws` endpoint
//! (`src/lorecraft/main.py::websocket_endpoint`, the behavior reference). Rust
//! owns the transport; Python owns credential/session/command policy behind the
//! gateway adapter (design decision 6). Per connection:
//!
//! 1. **Dedicated forward link.** The handler opens its **own**
//!    [`ForwardClient`] (one UDS connection to the Python adapter per player
//!    WebSocket — see `forward.rs`'s module docs for the resolved
//!    per-connection-link design decision).
//! 2. **Ticket auth.** The `?ticket=` query value (the single-use ticket minted
//!    by Python's `POST /auth/ws-ticket`) is forwarded as `RedeemTicket`. A
//!    rejected/absent/expired ticket closes with WS **1008**
//!    (`"Invalid or expired ticket"`), mirroring Python. There is deliberately
//!    **no** legacy `?player_id=` path.
//! 3. **Single live connection per player.** If the shared
//!    [`ConnectionRegistry`] already has this player, close **1008**
//!    (`"already_connected"`), mirroring `main.py`'s `is_connected` reject.
//! 4. **Connect handshake.** `Connected{player_id}` → `ConnectAck{session_id,
//!    room_id, direct_frames}`; the connection is registered and each
//!    `direct_frames` value (the legacy `connected` / `reconnect_sync` frames)
//!    is queued to the client ahead of any fan-out delivery.
//! 5. **Writer task.** One spawned task per connection owns the WS sink and
//!    drains the connection's bounded outbound queue (decision 9/10) — fan-out
//!    `try_send`s into the queue and never blocks on this client.
//! 6. **Receive loop.** Each inbound text frame becomes a [`CommandEnvelope`]
//!    (fresh Rust-minted `command_id`, per-connection monotonic
//!    `receive_sequence`) forwarded via [`ForwardClient::send_command`]; the
//!    `direct_reply` is queued back to this client. Side-effect `deliveries`
//!    are dispatched into the registry by the forward read loop and reach other
//!    players via *their* writer tasks.
//! 7. **Teardown.** On client close / receive error / writer exit: deregister,
//!    best-effort `Disconnected{reason: ClientClose}` to Python (its
//!    grace/flicker/`player_left` fan-out returns as `Deliver` pushes for the
//!    remaining players), then drain the writer.
//!
//! Deferred (noted, not silently dropped): graceful-quit detection — a command
//! whose reply indicates the player quit — still reports `ClientClose`; the
//! `GracefulQuit` tagging lands with the `POST /command` quit-path rerouting
//! (design decision 8). Mid-session internal errors (forward link death) drop
//! the socket abruptly (client sees 1006) rather than a crafted 1011 close,
//! because the sink is owned by the writer task; acceptable this phase.

use std::sync::Arc;

use axum::extract::ws::{close_code, CloseFrame, Message, Utf8Bytes, WebSocket, WebSocketUpgrade};
use axum::extract::{Query, State};
use axum::response::Response;
use futures_util::stream::SplitSink;
use futures_util::{SinkExt, StreamExt};
use lorecraft_events::outbound_channel;
use lorecraft_protocol::envelope::CommandEnvelope;
use lorecraft_protocol::gateway::DisconnectReason;
use lorecraft_protocol::ids::{ActorId, CommandId, PlayerId, WorldId};
use lorecraft_protocol::PROTOCOL_VERSION;
use serde::Deserialize;
use tokio::sync::mpsc;
use tokio::time::{timeout, Duration};
use uuid::Uuid;

use crate::auth::{self, AuthError};
use crate::forward::{ForwardClient, SessionAck};
use crate::gateway::{GatewayConfig, GatewayState};

/// The `/ws` upgrade query. Only `?ticket=` is supported — the legacy
/// `?player_id=` fallback (gated off by default in Python) is deliberately not
/// reproduced here.
#[derive(Debug, Deserialize)]
pub struct WsQuery {
    /// The single-use player WS ticket minted by Python's `POST /auth/ws-ticket`.
    #[serde(default)]
    ticket: Option<String>,
}

/// Handle a player `/ws` upgrade request.
///
/// Always accepts the upgrade and runs the auth handshake on the socket task, so
/// a bad ticket yields an application-level WS **1008** close (distinguishable
/// from a transport-level failure), mirroring the Python endpoint's
/// accept-then-close behavior.
pub async fn upgrade(
    ws: WebSocketUpgrade,
    Query(query): Query<WsQuery>,
    State(state): State<GatewayState>,
) -> Response {
    ws.on_upgrade(move |socket| handle_socket(socket, state, query.ticket))
}

/// Close the socket with an application-level close frame; best-effort.
async fn close_with(mut socket: WebSocket, code: u16, reason: &str) {
    let frame = CloseFrame {
        code,
        reason: Utf8Bytes::from(reason.to_owned()),
    };
    if let Err(err) = socket.send(Message::Close(Some(frame))).await {
        tracing::debug!(error = %err, code, "close frame not delivered");
    }
}

/// The full per-connection lifecycle (steps 1–7 in the module docs).
async fn handle_socket(socket: WebSocket, state: GatewayState, ticket: Option<String>) {
    let handshake_budget = Duration::from_millis(state.config.handshake_timeout_ms);

    // 1. Dedicated per-connection UDS link to the Python adapter.
    let forward = match ForwardClient::connect(
        &state.config.socket_path,
        Arc::clone(&state.registry),
    )
    .await
    {
        Ok(client) => client,
        Err(err) => {
            tracing::warn!(error = %err, "gateway backend unavailable for new connection");
            close_with(socket, close_code::ERROR, "gateway backend unavailable").await;
            return;
        }
    };

    // 2. Ticket auth: absent/empty and rejected tickets close identically (1008),
    //    mirroring Python's `_resolve_ws_player_id is None` path.
    let Some(ticket) = ticket.filter(|t| !t.is_empty()) else {
        close_with(socket, close_code::POLICY, "Invalid or expired ticket").await;
        return;
    };
    let player_id = match timeout(
        handshake_budget,
        auth::redeem_player_ticket(&forward, &ticket),
    )
    .await
    {
        Ok(Ok(player_id)) => player_id,
        Ok(Err(AuthError::Rejected)) => {
            close_with(socket, close_code::POLICY, "Invalid or expired ticket").await;
            return;
        }
        Ok(Err(AuthError::Transport)) | Err(_) => {
            close_with(socket, close_code::ERROR, "auth handoff failed").await;
            return;
        }
    };

    // 3. Single-live-connection rule (main.py ~466-483). Checked before the
    //    Connected handshake, matching Python's ordering. (Like Python, the check
    //    is not atomic with registration; two simultaneous upgrades for one
    //    player are a benign race the registry resolves by replacing the sender.)
    if state.registry.is_connected(&player_id) {
        close_with(socket, close_code::POLICY, "already_connected").await;
        return;
    }

    // 4. Connect handshake. The timeout is load-bearing: the adapter acks
    //    nothing for an unknown player this phase (it logs and returns no frame).
    let ack = match timeout(handshake_budget, forward.connect_session(player_id.clone())).await {
        Ok(Ok(ack)) => ack,
        Ok(Err(err)) => {
            tracing::warn!(error = %err, player_id = %player_id.0, "connect handshake failed");
            close_with(socket, close_code::ERROR, "connect handshake failed").await;
            return;
        }
        Err(_) => {
            tracing::warn!(player_id = %player_id.0, "connect handshake timed out");
            close_with(socket, close_code::ERROR, "connect handshake timed out").await;
            return;
        }
    };

    // Queue the direct frames (`connected`, and `reconnect_sync` on a grace
    // resume) BEFORE registering, so they are guaranteed to precede any fan-out
    // delivery in the outbound queue.
    let (outbound_tx, outbound_rx) = outbound_channel(state.config.outbound_queue_depth);
    for frame in &ack.direct_frames {
        if outbound_tx.send(frame.clone()).await.is_err() {
            // Unreachable in practice: we hold the receiver locally.
            tracing::error!(player_id = %player_id.0, "outbound queue closed before use");
            close_with(socket, close_code::ERROR, "internal error").await;
            return;
        }
    }
    state.registry.register(
        player_id.clone(),
        outbound_tx.clone(),
        Some(ack.room_id.clone()),
    );

    // 5. Split the socket; the writer task owns the sink and drains the queue.
    let (sink, mut stream) = socket.split();
    let writer = tokio::spawn(writer_task(sink, outbound_rx));

    // 6. Receive loop.
    let mut receive_sequence: u64 = 0;
    while let Some(incoming) = stream.next().await {
        match incoming {
            Ok(Message::Text(text)) => {
                receive_sequence += 1;
                let envelope = build_envelope(
                    &state.config,
                    &player_id,
                    &ack,
                    receive_sequence,
                    text.as_str(),
                );
                match forward.send_command(envelope).await {
                    Ok(direct_reply) => {
                        // Route the reply through this connection's own queue so
                        // it stays ordered with fan-out frames. A closed queue
                        // means the writer died (client unreadable): tear down.
                        if outbound_tx.send(direct_reply).await.is_err() {
                            tracing::debug!(
                                player_id = %player_id.0,
                                "writer gone; ending receive loop"
                            );
                            break;
                        }
                    }
                    Err(err) => {
                        tracing::warn!(
                            error = %err,
                            player_id = %player_id.0,
                            "command forward failed; dropping connection"
                        );
                        break;
                    }
                }
            }
            Ok(Message::Close(_)) => break,
            // Ping/pong are answered by the WS layer; binary frames have no
            // meaning on this protocol and are ignored, matching Python's
            // receive_text()-only loop.
            Ok(_) => {}
            Err(err) => {
                tracing::debug!(error = %err, player_id = %player_id.0, "receive error");
                break;
            }
        }
    }

    // 7. Teardown. Deregister first (stop new fan-out to this connection), then
    //    tell Python — its grace/flicker/player_left directives flow back on this
    //    same link and are dispatched to the *remaining* players; the directive
    //    aimed at this now-deregistered player is a harmless no-op.
    //    Graceful-quit detection is deferred (module docs): always ClientClose.
    state.registry.deregister(&player_id);
    if let Err(err) = forward
        .send_disconnected(player_id.clone(), DisconnectReason::ClientClose)
        .await
    {
        tracing::debug!(error = %err, player_id = %player_id.0, "disconnect notify failed");
    }
    // Let the writer drain and exit: dropping our sender closes the queue once
    // the registry's clone is gone too (deregistered above).
    drop(outbound_tx);
    if let Err(err) = writer.await {
        tracing::debug!(error = %err, player_id = %player_id.0, "writer task join error");
    }
}

/// The per-connection outbound writer (design decision 9/10): owns the WS sink,
/// drains the bounded queue, serializes each opaque payload as a **text** frame.
/// Exits on queue close (teardown) or a sink error (client unreadable) — the
/// latter surfaces to the receive loop as a closed queue on its next reply send.
async fn writer_task(
    mut sink: SplitSink<WebSocket, Message>,
    mut queue: mpsc::Receiver<serde_json::Value>,
) {
    while let Some(payload) = queue.recv().await {
        let text = payload.to_string();
        if let Err(err) = sink.send(Message::Text(Utf8Bytes::from(text))).await {
            tracing::debug!(error = %err, "outbound write failed; writer exiting");
            break;
        }
    }
}

/// Assemble the versioned [`CommandEnvelope`] for one inbound frame (design
/// decision 3 field sourcing): actor == player for a player command; the
/// `command_id` is a fresh Rust-minted UUID (idempotency key); `receive_sequence`
/// is the per-connection monotonic counter.
fn build_envelope(
    config: &GatewayConfig,
    player_id: &PlayerId,
    ack: &SessionAck,
    receive_sequence: u64,
    raw: &str,
) -> CommandEnvelope {
    CommandEnvelope {
        protocol_version: PROTOCOL_VERSION,
        world_id: WorldId(config.world_id.clone()),
        actor_id: ActorId(player_id.0.clone()),
        player_id: player_id.clone(),
        session_id: ack.session_id.clone(),
        command_id: CommandId(Uuid::new_v4().to_string()),
        receive_sequence,
        deadline_ms: config.default_deadline_ms,
        raw: raw.to_owned(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use lorecraft_protocol::ids::SessionId;

    #[test]
    fn build_envelope_stamps_identity_and_mints_unique_command_ids() {
        let config = GatewayConfig::default();
        let player = PlayerId("player-7".into());
        let ack = SessionAck {
            session_id: SessionId("sess-7".into()),
            room_id: "tavern".into(),
            direct_frames: vec![],
        };

        let first = build_envelope(&config, &player, &ack, 1, "look");
        let second = build_envelope(&config, &player, &ack, 2, "north");

        assert_eq!(first.protocol_version, PROTOCOL_VERSION);
        assert_eq!(first.world_id.0, config.world_id);
        assert_eq!(first.actor_id.0, "player-7");
        assert_eq!(first.player_id, player);
        assert_eq!(first.session_id.0, "sess-7");
        assert_eq!(first.receive_sequence, 1);
        assert_eq!(second.receive_sequence, 2);
        assert_eq!(first.deadline_ms, config.default_deadline_ms);
        assert_eq!(first.raw, "look");
        assert_ne!(
            first.command_id, second.command_id,
            "command ids must be unique per command"
        );
    }
}
