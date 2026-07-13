//! `forward.rs` — the Rust-side UDS forwarding client to the Python adapter.
//!
//! This is the counterpart to `src/lorecraft/gateway/adapter.py`'s
//! `asyncio.start_unix_server` listener. It speaks the identical framed protocol:
//! a **4-byte big-endian length prefix** followed by **UTF-8 JSON** for each frame
//! (see [`read_frame`]/[`write_frame`]). It writes [`GatewayInbound`] frames and
//! reads [`GatewayOutbound`] frames back on one long-lived [`UnixStream`].
//!
//! ## Request/reply multiplexing (design decision 4 / OPEN ITEM 1)
//!
//! Python multiplexes two kinds of outbound frame on the same connection:
//!
//! - a **correlated** [`GatewayOutbound::CommandReply`], carrying the
//!   [`CommandId`] of the [`GatewayInbound::Command`] it answers, and
//! - **un-correlated** async pushes ([`GatewayOutbound::Deliver`], and — in later
//!   phases — [`GatewayOutbound::AuthResult`]/[`GatewayOutbound::ConnectAck`]),
//!   which are not replies to any specific inbound frame.
//!
//! A single background **read loop** ([`read_loop`]) demultiplexes them:
//!
//! - A `CommandReply` completes the pending request keyed by `command_id` — a
//!   [`oneshot::Sender`] stored in a shared `HashMap<String, _>` (keyed by the
//!   `command_id` string; [`CommandId`](lorecraft_protocol::ids::CommandId) is not
//!   `Hash`) — so whichever caller sent that command receives its `direct_reply`.
//!   Its own `deliveries` are **also**
//!   relayed into the shared [`ConnectionRegistry`] via
//!   [`lorecraft_events::dispatch`] as an independent side effect.
//! - A `Deliver` has no pending request to complete, so its `directive` is relayed
//!   straight into the registry.
//!
//! Writes are serialized behind a [`tokio::sync::Mutex`] on the write half so
//! concurrent [`ForwardClient::send_command`] callers never interleave frames.

use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;

use lorecraft_events::{dispatch, ConnectionRegistry};
use lorecraft_protocol::envelope::CommandEnvelope;
use lorecraft_protocol::gateway::{GatewayInbound, GatewayOutbound};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::unix::{OwnedReadHalf, OwnedWriteHalf};
use tokio::net::UnixStream;
use tokio::sync::{oneshot, Mutex};
use tokio::task::JoinHandle;

const LENGTH_PREFIX_BYTES: usize = 4;

/// A map of in-flight command ids to the oneshot that resolves the caller.
///
/// Keyed by the raw `command_id` string because
/// [`CommandId`](lorecraft_protocol::ids::CommandId) does not derive `Hash` in the
/// protocol crate.
type PendingReplies = Arc<Mutex<HashMap<String, oneshot::Sender<GatewayOutbound>>>>;

/// A failure of the forwarding client.
#[derive(Debug, thiserror::Error)]
pub enum ForwardError {
    /// The underlying UDS connection failed (connect, read, or write I/O).
    #[error("gateway transport i/o error: {0}")]
    Io(#[from] std::io::Error),
    /// A frame could not be (de)serialized to/from JSON.
    #[error("gateway frame (de)serialization failed: {0}")]
    Serde(#[from] serde_json::Error),
    /// A frame's body exceeded the `u32` length prefix's capacity.
    #[error("gateway frame body too large: {0} bytes")]
    FrameTooLarge(usize),
    /// The read loop ended (peer closed / connection dropped) before a reply
    /// arrived, so the pending request can never be completed.
    #[error("gateway connection closed before reply")]
    ConnectionClosed,
    /// A reply arrived on a command's correlation slot that was not a
    /// [`GatewayOutbound::CommandReply`] — a protocol violation.
    #[error("unexpected non-CommandReply frame answered a command")]
    UnexpectedReply,
}

/// The Rust-side framed UDS client that forwards commands to the Python adapter
/// and relays its fan-out directives into the connection registry.
pub struct ForwardClient {
    /// The write half, guarded so concurrent senders serialize their frames.
    write: Mutex<OwnedWriteHalf>,
    /// In-flight command correlation slots (see [`PendingReplies`]).
    pending: PendingReplies,
    /// The background demultiplexing read loop; aborted on drop.
    read_task: JoinHandle<()>,
}

impl ForwardClient {
    /// Connect to the Python adapter's UDS listener at `socket_path` and spawn the
    /// background read loop that demultiplexes replies against `registry`.
    ///
    /// The returned client is ready to [`send_command`](Self::send_command)
    /// immediately; async pushes and command-reply side-effect deliveries begin
    /// flowing into `registry` as soon as Python emits them.
    pub async fn connect(
        socket_path: impl AsRef<Path>,
        registry: Arc<ConnectionRegistry>,
    ) -> Result<Self, ForwardError> {
        let stream = UnixStream::connect(socket_path).await?;
        let (read, write) = stream.into_split();
        let pending: PendingReplies = Arc::new(Mutex::new(HashMap::new()));
        let read_task = tokio::spawn(read_loop(read, registry, Arc::clone(&pending)));
        Ok(Self {
            write: Mutex::new(write),
            pending,
            read_task,
        })
    }

    /// Forward one [`CommandEnvelope`] to Python and await its correlated
    /// [`GatewayOutbound::CommandReply`], returning just the opaque `direct_reply`.
    ///
    /// The reply's side-effect `deliveries` are dispatched into the registry
    /// independently by the read loop, so they are already fanned out by the time
    /// this returns; the caller only receives the payload destined for the issuing
    /// client.
    pub async fn send_command(
        &self,
        envelope: CommandEnvelope,
    ) -> Result<serde_json::Value, ForwardError> {
        let command_key = envelope.command_id.0.clone();
        let (tx, rx) = oneshot::channel();
        self.pending.lock().await.insert(command_key.clone(), tx);

        // Write the framed Command; on failure, reclaim the pending slot so it does
        // not leak and a retry can reuse the id.
        if let Err(err) = self.write_frame(&GatewayInbound::Command(envelope)).await {
            self.pending.lock().await.remove(&command_key);
            return Err(err);
        }

        match rx.await {
            Ok(GatewayOutbound::CommandReply { direct_reply, .. }) => Ok(direct_reply),
            Ok(_) => Err(ForwardError::UnexpectedReply),
            // The sender was dropped without sending: the read loop ended (peer
            // closed / decode error) with this request still in flight.
            Err(_) => Err(ForwardError::ConnectionClosed),
        }
    }

    /// Whether the background read loop is still running (the link to Python is
    /// live). Cheap, non-blocking — used by the gateway health check.
    pub fn is_active(&self) -> bool {
        !self.read_task.is_finished()
    }

    /// Serialize `frame` and write it length-prefixed under the write lock.
    async fn write_frame(&self, frame: &GatewayInbound) -> Result<(), ForwardError> {
        let body = serde_json::to_vec(frame)?;
        let len = u32::try_from(body.len()).map_err(|_| ForwardError::FrameTooLarge(body.len()))?;
        let mut write = self.write.lock().await;
        write.write_all(&len.to_be_bytes()).await?;
        write.write_all(&body).await?;
        write.flush().await?;
        Ok(())
    }
}

impl Drop for ForwardClient {
    fn drop(&mut self) {
        // Stop the detached read loop when the client goes away.
        self.read_task.abort();
    }
}

/// The background demultiplexer: read frames until the peer closes or a frame
/// fails to decode, routing each to its pending request or the registry.
///
/// On exit it drops every still-pending oneshot sender, which surfaces as
/// [`ForwardError::ConnectionClosed`] to any caller blocked in
/// [`ForwardClient::send_command`] — a dropped connection never hangs a caller.
async fn read_loop(
    mut read: OwnedReadHalf,
    registry: Arc<ConnectionRegistry>,
    pending: PendingReplies,
) {
    loop {
        match read_frame(&mut read).await {
            Ok(Some(frame)) => demultiplex(frame, &registry, &pending).await,
            Ok(None) => break, // clean end-of-stream: peer closed
            Err(err) => {
                // Not silent: a decode/transport fault ends the link, and the
                // pending-slot drain below fails every in-flight caller.
                tracing::warn!(error = %err, "gateway read loop terminating on frame error");
                break;
            }
        }
    }
    // Fail all in-flight requests: dropping the senders wakes their receivers.
    pending.lock().await.clear();
}

/// Route one decoded outbound frame to its pending request and/or the registry.
async fn demultiplex(
    frame: GatewayOutbound,
    registry: &ConnectionRegistry,
    pending: &PendingReplies,
) {
    match frame {
        GatewayOutbound::CommandReply {
            command_id,
            direct_reply,
            deliveries,
        } => {
            // Side-effect fan-out is dispatched independently of the caller's reply.
            for directive in &deliveries {
                let report = dispatch(registry, directive);
                if !report.is_clean() {
                    tracing::warn!(
                        failures = report.failures.len(),
                        "command-reply delivery had non-silent failures"
                    );
                }
            }
            let waiter = pending.lock().await.remove(&command_id.0);
            match waiter {
                Some(tx) => {
                    // Reconstruct and forward the full frame; the caller extracts
                    // `direct_reply` (later phases may inspect more).
                    let _ = tx.send(GatewayOutbound::CommandReply {
                        command_id,
                        direct_reply,
                        deliveries,
                    });
                }
                None => tracing::warn!(
                    command_id = %command_id.0,
                    "command reply had no matching pending request"
                ),
            }
        }
        GatewayOutbound::Deliver { directive } => {
            let report = dispatch(registry, &directive);
            if !report.is_clean() {
                tracing::warn!(
                    failures = report.failures.len(),
                    "async deliver had non-silent failures"
                );
            }
        }
        // Correlated auth/session handshakes are handled by the ws_player (3b) and
        // ws_admin (3c) cutovers; in 3a no RedeemTicket/Connected is ever sent, so
        // these are unexpected here rather than silently meaningful.
        GatewayOutbound::AuthResult { .. } => {
            tracing::debug!("received AuthResult; auth handoff lands in Phase 3b/3c");
        }
        GatewayOutbound::ConnectAck { .. } => {
            tracing::debug!("received ConnectAck; connection lifecycle lands in Phase 3b");
        }
    }
}

/// Read one length-prefixed frame, or `Ok(None)` at a clean end-of-stream.
///
/// A peer that closes exactly on a frame boundary yields `Ok(None)`; a close
/// mid-frame is a real truncation error.
async fn read_frame(read: &mut OwnedReadHalf) -> Result<Option<GatewayOutbound>, ForwardError> {
    let mut header = [0u8; LENGTH_PREFIX_BYTES];
    match read.read_exact(&mut header).await {
        Ok(_) => {}
        Err(err) if err.kind() == std::io::ErrorKind::UnexpectedEof => return Ok(None),
        Err(err) => return Err(err.into()),
    }
    let len = u32::from_be_bytes(header) as usize;
    let mut body = vec![0u8; len];
    read.read_exact(&mut body).await?;
    let frame = serde_json::from_slice::<GatewayOutbound>(&body)?;
    Ok(Some(frame))
}

/// Serialize `frame` as a length-prefixed frame into `buf` (test/helper mirror of
/// [`ForwardClient::write_frame`], reused by the mock peer in tests).
#[cfg(test)]
fn encode_frame(frame: &GatewayOutbound) -> Vec<u8> {
    let body = serde_json::to_vec(frame).expect("serialize outbound frame");
    let len = u32::try_from(body.len()).expect("frame fits u32");
    let mut out = Vec::with_capacity(LENGTH_PREFIX_BYTES + body.len());
    out.extend_from_slice(&len.to_be_bytes());
    out.extend_from_slice(&body);
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use lorecraft_events::{outbound_channel, DEFAULT_OUTBOUND_QUEUE_DEPTH};
    use lorecraft_protocol::gateway::{DeliveryDirective, DeliveryTarget, GatewayInbound};
    use lorecraft_protocol::ids::{ActorId, CommandId, PlayerId, SessionId, WorldId};
    use lorecraft_protocol::PROTOCOL_VERSION;
    use serde_json::json;
    use tokio::net::UnixListener;

    fn sample_envelope(command_id: &str, raw: &str) -> CommandEnvelope {
        CommandEnvelope {
            protocol_version: PROTOCOL_VERSION,
            world_id: WorldId("world-1".into()),
            actor_id: ActorId("actor-1".into()),
            player_id: PlayerId("player-1".into()),
            session_id: SessionId("session-1".into()),
            command_id: CommandId(command_id.into()),
            receive_sequence: 7,
            deadline_ms: 5_000,
            raw: raw.into(),
        }
    }

    /// Read one length-prefixed frame from a raw stream half (mock-peer side).
    async fn read_inbound(read: &mut OwnedReadHalf) -> GatewayInbound {
        let mut header = [0u8; LENGTH_PREFIX_BYTES];
        read.read_exact(&mut header).await.expect("read header");
        let len = u32::from_be_bytes(header) as usize;
        let mut body = vec![0u8; len];
        read.read_exact(&mut body).await.expect("read body");
        serde_json::from_slice(&body).expect("decode inbound")
    }

    /// THE CHECKLIST INTEGRATION PROOF: a mock UDS peer stands in for the Python
    /// adapter. The `ForwardClient` sends a `Command`; the peer replies with a
    /// framed `CommandReply` carrying a `direct_reply` and one `DeliveryDirective`.
    /// Assert (a) `send_command` returns the `direct_reply`, and (b) the delivery
    /// actually landed in the `ConnectionRegistry` (a pre-registered fake recipient
    /// receives the payload on its outbound channel).
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn send_command_returns_reply_and_relays_deliveries() {
        let dir = tempfile::tempdir().expect("tempdir");
        let socket_path = dir.path().join("gateway.sock");
        let listener = UnixListener::bind(&socket_path).expect("bind mock peer");

        // Registry with a pre-registered recipient the delivery will target.
        let registry = Arc::new(ConnectionRegistry::new());
        let (recipient_tx, mut recipient_rx) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        registry.register(
            PlayerId("player-1".into()),
            recipient_tx,
            Some("tavern".into()),
        );

        // Mock Python adapter: accept one connection, read the Command, reply with a
        // correlated CommandReply carrying a room-targeted delivery.
        let peer = tokio::spawn(async move {
            let (stream, _) = listener.accept().await.expect("accept");
            let (mut read, mut write) = stream.into_split();
            let inbound = read_inbound(&mut read).await;
            let command_id = match inbound {
                GatewayInbound::Command(env) => {
                    assert_eq!(env.raw, "look");
                    env.command_id
                }
                other => panic!("expected Command, got {other:?}"),
            };
            let reply = GatewayOutbound::CommandReply {
                command_id,
                direct_reply: json!({"command": "look", "messages": ["a dim tavern"]}),
                deliveries: vec![DeliveryDirective {
                    target: DeliveryTarget::Room {
                        id: "tavern".into(),
                    },
                    exclude: None,
                    payload: json!({"type": "feed_append", "text": "someone looks around."}),
                }],
            };
            write
                .write_all(&encode_frame(&reply))
                .await
                .expect("write reply");
            write.flush().await.expect("flush reply");
            // Hold the connection open so the client's read loop stays alive.
            tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        });

        let client = ForwardClient::connect(&socket_path, Arc::clone(&registry))
            .await
            .expect("connect");

        let direct_reply = client
            .send_command(sample_envelope("cmd-1", "look"))
            .await
            .expect("send_command");

        // (a) The caller got the direct reply.
        assert_eq!(
            direct_reply,
            json!({"command": "look", "messages": ["a dim tavern"]})
        );

        // (b) The side-effect delivery landed in the registry / recipient channel.
        let delivered =
            tokio::time::timeout(std::time::Duration::from_secs(2), recipient_rx.recv())
                .await
                .expect("recipient receives without stalling")
                .expect("a payload was delivered");
        assert_eq!(
            delivered,
            json!({"type": "feed_append", "text": "someone looks around."})
        );

        peer.await.expect("mock peer joins cleanly");
    }

    /// A dropped connection must fail an in-flight caller with `ConnectionClosed`
    /// rather than hang it forever.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn dropped_connection_fails_pending_caller() {
        let dir = tempfile::tempdir().expect("tempdir");
        let socket_path = dir.path().join("gateway.sock");
        let listener = UnixListener::bind(&socket_path).expect("bind mock peer");

        // Peer accepts, reads the command, then closes WITHOUT replying.
        let peer = tokio::spawn(async move {
            let (stream, _) = listener.accept().await.expect("accept");
            let (mut read, write) = stream.into_split();
            let _ = read_inbound(&mut read).await;
            drop(write);
            drop(read);
        });

        let registry = Arc::new(ConnectionRegistry::new());
        let client = ForwardClient::connect(&socket_path, registry)
            .await
            .expect("connect");

        let result = client.send_command(sample_envelope("cmd-2", "look")).await;
        assert!(matches!(result, Err(ForwardError::ConnectionClosed)));

        peer.await.expect("mock peer joins cleanly");
    }
}
