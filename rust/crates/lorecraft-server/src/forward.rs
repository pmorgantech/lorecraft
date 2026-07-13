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
//! - An `AuthResult` or `ConnectAck` completes the single **pending control
//!   slot** (see below) — no correlation id is needed for these.
//! - A `Deliver` has no pending request to complete, so its `directive` is relayed
//!   straight into the registry.
//!
//! Writes are serialized behind a [`tokio::sync::Mutex`] on the write half so
//! concurrent [`ForwardClient::send_command`] callers never interleave frames.
//!
//! ## One `ForwardClient` per player connection (Phase 3b resolution)
//!
//! **Resolved design choice:** each player WebSocket connection opens its **own
//! dedicated `ForwardClient`** (its own UDS connection to the Python adapter),
//! rather than multiplexing every player over one shared link. Rationale:
//!
//! - The `RedeemTicket → AuthResult` and `Connected → ConnectAck` handshake steps
//!   arrive strictly **in order** on the dedicated link (at most one handshake
//!   step is ever outstanding per link), so no correlation id is needed for
//!   auth/connect — a single pending-control-reply slot suffices.
//! - `Command → CommandReply` still correlates by `command_id` (kept from 3a),
//!   which also keeps the client correct if it is ever shared.
//! - The link's own async `Deliver` pushes are routed into the **shared**
//!   [`ConnectionRegistry`], so cross-player deliveries produced on the *acting*
//!   player's link (as `CommandReply.deliveries` or standalone `Deliver`s) are
//!   fanned out to every recipient's outbound queue — a player never needs a
//!   frame routed down some *other* player's link.
//!
//! The Python adapter (`src/lorecraft/gateway/adapter.py`) serves each accepted
//! UDS connection independently (`asyncio.start_unix_server`) against one shared
//! directive-recording manager, so N concurrent links are supported by design.

use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;

use lorecraft_events::dispatch_with_config;
use lorecraft_protocol::envelope::{CommandEnvelope, CommandOutcome};
use lorecraft_protocol::gateway::{DisconnectReason, GatewayInbound, GatewayOutbound};
use lorecraft_protocol::ids::{CommandId, PlayerId, SessionId};
use lorecraft_protocol::script::ScriptRequest;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::unix::{OwnedReadHalf, OwnedWriteHalf};
use tokio::net::UnixStream;
use tokio::sync::{oneshot, Mutex};
use tokio::task::JoinHandle;

use crate::disconnect::DispatchContext;

const LENGTH_PREFIX_BYTES: usize = 4;

/// A map of in-flight command ids to the oneshot that resolves the caller.
///
/// Keyed by the raw `command_id` string because
/// [`CommandId`](lorecraft_protocol::ids::CommandId) does not derive `Hash` in the
/// protocol crate.
type PendingReplies = Arc<Mutex<HashMap<String, oneshot::Sender<GatewayOutbound>>>>;

/// A map of in-flight **execution** round-trips (Phase 4) to the oneshot that
/// resolves the driver awaiting a `SnapshotReady`/`OutcomeApplied`.
///
/// Keyed by the raw `command_id` string, exactly like [`PendingReplies`]. The two
/// legs of one command's round-trip (`BuildSnapshot → SnapshotReady`, then
/// `ApplyOutcome → OutcomeApplied`) are strictly sequential — the driver awaits the
/// snapshot before sending the outcome — so one slot per `command_id` is reused
/// across both legs with no collision.
type PendingExec = Arc<Mutex<HashMap<String, oneshot::Sender<GatewayOutbound>>>>;

/// The single pending **control** reply slot for the sequential
/// `RedeemTicket → AuthResult` / `Connected → ConnectAck` handshake steps.
///
/// Per-link handshakes are strictly sequential (at most one outstanding — see the
/// module docs), so one slot suffices; no keyed correlation map is needed.
type PendingControl = Arc<Mutex<Option<oneshot::Sender<GatewayOutbound>>>>;

/// The single pending **disconnect-completion** slot.
///
/// A `Disconnected` teardown is answered by exactly one terminal
/// [`GatewayOutbound::DisconnectAck`], emitted *after* the teardown's fan-out
/// `Deliver`s. A link disconnects exactly once, so one slot suffices. Completing
/// it lets [`ForwardClient::send_disconnected`] return only once every teardown
/// `Deliver` has been read and dispatched into the shared registry (i.e. the
/// remaining room siblings have already received the leave).
type PendingDisconnect = Arc<Mutex<Option<oneshot::Sender<()>>>>;

/// The decoded outcome of a `RedeemTicket` (or `ValidateAdminToken`) handoff.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuthDecision {
    /// Whether Python accepted the credential.
    pub accepted: bool,
    /// The authenticated player on acceptance (player-ticket path), else `None`.
    pub player_id: Option<PlayerId>,
}

/// The decoded acknowledgement of a `Connected` lifecycle handshake.
#[derive(Debug, Clone, PartialEq)]
pub struct SessionAck {
    /// The session Python minted or resumed for this connection.
    pub session_id: SessionId,
    /// The room the player is currently in.
    pub room_id: String,
    /// Opaque legacy frames to deliver directly to the connecting client
    /// (`connected`, plus `reconnect_sync` on a grace resume).
    pub direct_frames: Vec<serde_json::Value>,
}

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
    /// A second control round-trip (`RedeemTicket`/`Connected`, or the
    /// `Disconnected` teardown) was started while one was still pending on this
    /// link — a caller bug, since these are strictly one-at-a-time per link (see
    /// the module docs).
    #[error("a control round-trip is already in flight on this link")]
    HandshakeInFlight,
}

/// The Rust-side framed UDS client that forwards commands to the Python adapter
/// and relays its fan-out directives into the connection registry.
pub struct ForwardClient {
    /// The write half, guarded so concurrent senders serialize their frames.
    write: Mutex<OwnedWriteHalf>,
    /// In-flight command correlation slots (see [`PendingReplies`]).
    pending: PendingReplies,
    /// In-flight execution round-trip slots (Phase 4; see [`PendingExec`]).
    exec: PendingExec,
    /// The single pending control-handshake slot (see [`PendingControl`]).
    control: PendingControl,
    /// The single pending disconnect-completion slot (see [`PendingDisconnect`]).
    disconnect: PendingDisconnect,
    /// The background demultiplexing read loop; aborted on drop.
    read_task: JoinHandle<()>,
}

impl ForwardClient {
    /// Connect to the Python adapter's UDS listener at `socket_path` and spawn the
    /// background read loop that demultiplexes replies against `ctx`.
    ///
    /// The returned client is ready to [`send_command`](Self::send_command)
    /// immediately; async pushes and command-reply side-effect deliveries begin
    /// flowing into `ctx.registry` as soon as Python emits them, and a
    /// slow-consumer overflow reported by [`dispatch_with_config`] is propagated to
    /// the offending connection's writer via `ctx.disconnect` (Phase 3c, item 3).
    pub async fn connect(
        socket_path: impl AsRef<Path>,
        ctx: DispatchContext,
    ) -> Result<Self, ForwardError> {
        let stream = UnixStream::connect(socket_path).await?;
        let (read, write) = stream.into_split();
        let pending: PendingReplies = Arc::new(Mutex::new(HashMap::new()));
        let exec: PendingExec = Arc::new(Mutex::new(HashMap::new()));
        let control: PendingControl = Arc::new(Mutex::new(None));
        let disconnect: PendingDisconnect = Arc::new(Mutex::new(None));
        let read_task = tokio::spawn(read_loop(
            read,
            ctx,
            Arc::clone(&pending),
            Arc::clone(&exec),
            Arc::clone(&control),
            Arc::clone(&disconnect),
        ));
        Ok(Self {
            write: Mutex::new(write),
            pending,
            exec,
            control,
            disconnect,
            read_task,
        })
    }

    /// Redeem a single-use player WS ticket: write a
    /// [`GatewayInbound::RedeemTicket`] and await the routed
    /// [`GatewayOutbound::AuthResult`].
    pub async fn redeem_ticket(&self, ticket: &str) -> Result<AuthDecision, ForwardError> {
        let frame = GatewayInbound::RedeemTicket {
            ticket: ticket.to_owned(),
        };
        match self.send_control(frame).await? {
            GatewayOutbound::AuthResult {
                accepted,
                player_id,
            } => Ok(AuthDecision {
                accepted,
                player_id,
            }),
            _ => Err(ForwardError::UnexpectedReply),
        }
    }

    /// Validate an admin `?token=` JWT: write a
    /// [`GatewayInbound::ValidateAdminToken`] and await the routed shape-distinct
    /// [`GatewayOutbound::AdminAuthResult`], returning whether Python accepted it.
    ///
    /// The admin result carries no `player_id` (admin tokens are not player-scoped),
    /// so — unlike [`redeem_ticket`](Self::redeem_ticket) — there is no player to
    /// resolve; a validated admin is registered by the caller into the Rust-local
    /// admin registry (see the resolved admin-push design in
    /// `lorecraft-protocol::gateway`).
    pub async fn validate_admin(&self, token: &str) -> Result<bool, ForwardError> {
        let frame = GatewayInbound::ValidateAdminToken {
            token: token.to_owned(),
        };
        match self.send_control(frame).await? {
            GatewayOutbound::AdminAuthResult { accepted } => Ok(accepted),
            _ => Err(ForwardError::UnexpectedReply),
        }
    }

    /// Run the `Connected` lifecycle handshake: write a
    /// [`GatewayInbound::Connected`] and await the routed
    /// [`GatewayOutbound::ConnectAck`].
    ///
    /// **Caller must apply a timeout**: the Python adapter acks *nothing* for an
    /// unknown player or a missing room this phase (it logs and returns no
    /// frame), so an un-timed await could hang forever.
    pub async fn connect_session(&self, player_id: PlayerId) -> Result<SessionAck, ForwardError> {
        let frame = GatewayInbound::Connected { player_id };
        match self.send_control(frame).await? {
            GatewayOutbound::ConnectAck {
                session_id,
                room_id,
                direct_frames,
            } => Ok(SessionAck {
                session_id,
                room_id,
                direct_frames,
            }),
            _ => Err(ForwardError::UnexpectedReply),
        }
    }

    /// Notify Python that this player's connection ended, then **await the
    /// teardown's completion** before returning.
    ///
    /// This is a request/complete handshake, not fire-and-forget: the teardown's
    /// own fan-out (`player_left`, the connection-flicker narration, the
    /// `players-online` refresh, follow-break notices) flows back on this same
    /// link as `Deliver` pushes, which the read loop dispatches into the shared
    /// registry — reaching the *remaining* room siblings. Python then emits a
    /// terminal [`GatewayOutbound::DisconnectAck`] *after* those `Deliver`s; this
    /// method awaits it, so it returns only once every teardown `Deliver` has been
    /// read and dispatched. That is what lets the caller drop this dying
    /// per-connection link **without** racing the read loop's abort against those
    /// still-in-flight `Deliver`s (the bug this handshake fixes).
    ///
    /// **Caller must apply a timeout**: a pathological or slow adapter that never
    /// sends the ack must not wedge teardown forever. On the read loop dying first
    /// this returns [`ForwardError::ConnectionClosed`] rather than hanging.
    pub async fn send_disconnected(
        &self,
        player_id: PlayerId,
        reason: DisconnectReason,
    ) -> Result<(), ForwardError> {
        let (tx, rx) = oneshot::channel();
        {
            // A link disconnects exactly once; a second call is a caller bug.
            let mut slot = self.disconnect.lock().await;
            if slot.is_some() {
                return Err(ForwardError::HandshakeInFlight);
            }
            *slot = Some(tx);
        }
        if let Err(err) = self
            .write_frame(&GatewayInbound::Disconnected { player_id, reason })
            .await
        {
            // Reclaim the slot so the failure is clean (the link is torn down next).
            self.disconnect.lock().await.take();
            return Err(err);
        }
        // Completes on the terminal `DisconnectAck` (all teardown `Deliver`s
        // dispatched first). A dropped sender means the read loop ended.
        rx.await.map_err(|_| ForwardError::ConnectionClosed)
    }

    /// Write a control frame and await the single routed control reply.
    ///
    /// Per-link control handshakes are strictly sequential (module docs), so the
    /// slot being occupied is a caller bug surfaced as
    /// [`ForwardError::HandshakeInFlight`], never silently overwritten.
    async fn send_control(&self, frame: GatewayInbound) -> Result<GatewayOutbound, ForwardError> {
        let (tx, rx) = oneshot::channel();
        {
            let mut slot = self.control.lock().await;
            if slot.is_some() {
                return Err(ForwardError::HandshakeInFlight);
            }
            *slot = Some(tx);
        }
        if let Err(err) = self.write_frame(&frame).await {
            // Reclaim the slot so a retry on this link is possible.
            self.control.lock().await.take();
            return Err(err);
        }
        // Sender dropped without sending: the read loop ended mid-handshake.
        rx.await.map_err(|_| ForwardError::ConnectionClosed)
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

    /// Phase 4 leg 1 (Option A): send [`GatewayInbound::BuildSnapshot`] for
    /// `envelope` and await the correlated [`GatewayOutbound::SnapshotReady`],
    /// returning the materialized [`ScriptRequest`] the migrated feature executes
    /// against.
    ///
    /// Correlated by `command_id` (= `envelope.command_id`) through the
    /// [`PendingExec`] map, the same way [`send_command`](Self::send_command)
    /// correlates a `CommandReply`.
    pub async fn build_snapshot(
        &self,
        envelope: CommandEnvelope,
    ) -> Result<Box<ScriptRequest>, ForwardError> {
        let command_key = envelope.command_id.0.clone();
        let frame = GatewayInbound::BuildSnapshot { envelope };
        match self.send_exec(frame, command_key).await? {
            GatewayOutbound::SnapshotReady { request, .. } => Ok(request),
            _ => Err(ForwardError::UnexpectedReply),
        }
    }

    /// Phase 4 leg 2 (Option A): send [`GatewayInbound::ApplyOutcome`] and await the
    /// terminal [`GatewayOutbound::OutcomeApplied`], returning the opaque legacy
    /// `direct_reply` for the issuing client.
    ///
    /// The reply's post-commit `deliveries` are dispatched into the shared registry
    /// **by the read loop** (see [`demultiplex`]) — the same independent side-effect
    /// fan-out a `CommandReply`'s deliveries take — so by the time this returns they
    /// are already published. Commit-before-publish holds because Python commits
    /// both DBs before emitting `OutcomeApplied`.
    pub async fn apply_outcome(
        &self,
        command_id: CommandId,
        outcome: CommandOutcome,
    ) -> Result<serde_json::Value, ForwardError> {
        let command_key = command_id.0.clone();
        let frame = GatewayInbound::ApplyOutcome {
            command_id,
            outcome,
        };
        match self.send_exec(frame, command_key).await? {
            GatewayOutbound::OutcomeApplied { direct_reply, .. } => Ok(direct_reply),
            _ => Err(ForwardError::UnexpectedReply),
        }
    }

    /// Register an execution round-trip slot keyed by `command_key`, write `frame`,
    /// and await the routed [`GatewayOutbound`] reply (`SnapshotReady` or
    /// `OutcomeApplied`). On a write failure the slot is reclaimed so a retry can
    /// reuse the id; a dropped sender (read loop ended) surfaces as
    /// [`ForwardError::ConnectionClosed`] rather than hanging.
    async fn send_exec(
        &self,
        frame: GatewayInbound,
        command_key: String,
    ) -> Result<GatewayOutbound, ForwardError> {
        let (tx, rx) = oneshot::channel();
        self.exec.lock().await.insert(command_key.clone(), tx);
        if let Err(err) = self.write_frame(&frame).await {
            self.exec.lock().await.remove(&command_key);
            return Err(err);
        }
        rx.await.map_err(|_| ForwardError::ConnectionClosed)
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
    ctx: DispatchContext,
    pending: PendingReplies,
    exec: PendingExec,
    control: PendingControl,
    disconnect: PendingDisconnect,
) {
    loop {
        match read_frame(&mut read).await {
            Ok(Some(frame)) => {
                demultiplex(frame, &ctx, &pending, &exec, &control, &disconnect).await
            }
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
    exec.lock().await.clear();
    control.lock().await.take();
    disconnect.lock().await.take();
}

/// Route one decoded outbound frame to its pending request and/or the registry.
async fn demultiplex(
    frame: GatewayOutbound,
    ctx: &DispatchContext,
    pending: &PendingReplies,
    exec: &PendingExec,
    control: &PendingControl,
    disconnect: &PendingDisconnect,
) {
    match frame {
        GatewayOutbound::CommandReply {
            command_id,
            direct_reply,
            deliveries,
        } => {
            // Side-effect fan-out is dispatched independently of the caller's reply.
            for directive in &deliveries {
                relay_directive(ctx, directive);
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
            relay_directive(ctx, &directive);
        }
        // A registry state update, not a delivery: reconcile the mover's room in
        // the shared authoritative map so a *subsequent* room-targeted broadcast
        // aimed at their new room resolves them as a member. Because the read loop
        // processes frames in order and Python emits this ahead of the moving
        // command's own deliveries down the same link, the map is already updated
        // before any later `Deliver`/`CommandReply` is resolved against it.
        GatewayOutbound::MovePlayer {
            player_id,
            from_room,
            to_room,
        } => {
            ctx.registry
                .move_player(&player_id, from_room.as_deref(), &to_room);
        }
        // Control replies for the sequential per-link handshakes: complete the
        // single pending control slot. An unsolicited one (no waiter) is a
        // protocol anomaly worth surfacing, never silently dropped.
        // `AdminAuthResult` is the admin channel's control reply and routes the
        // same way; Phase 3c task 2 wires the admin handshake that awaits it.
        frame @ (GatewayOutbound::AuthResult { .. }
        | GatewayOutbound::AdminAuthResult { .. }
        | GatewayOutbound::ConnectAck { .. }) => {
            let waiter = control.lock().await.take();
            match waiter {
                Some(tx) => {
                    let _ = tx.send(frame);
                }
                None => tracing::warn!("control reply arrived with no pending handshake"),
            }
        }
        // The terminal teardown ack: complete the disconnect waiter. Because the
        // read loop processes frames in order, every teardown `Deliver` above has
        // already been dispatched by the time this arrives. An unsolicited ack
        // (no waiter) is a protocol anomaly worth surfacing, never silently dropped.
        GatewayOutbound::DisconnectAck => {
            let waiter = disconnect.lock().await.take();
            match waiter {
                Some(tx) => {
                    let _ = tx.send(());
                }
                None => tracing::warn!("disconnect ack arrived with no pending teardown"),
            }
        }
        // Phase 4 execution round-trip replies (Option A). Both correlate to the
        // executing command by `command_id` through the `exec` map — the same shape
        // as `CommandReply`'s `pending` map — completing the driver leg awaiting in
        // `ForwardClient::build_snapshot` / `apply_outcome`. An unsolicited one (no
        // waiter) is a protocol anomaly worth surfacing, never silently dropped.
        GatewayOutbound::SnapshotReady {
            command_id,
            request,
        } => {
            let key = command_id.0.clone();
            let waiter = exec.lock().await.remove(&key);
            match waiter {
                Some(tx) => {
                    let _ = tx.send(GatewayOutbound::SnapshotReady {
                        command_id,
                        request,
                    });
                }
                None => tracing::warn!(
                    command_id = %key,
                    "snapshot-ready reply had no matching pending execution"
                ),
            }
        }
        GatewayOutbound::OutcomeApplied {
            command_id,
            direct_reply,
            deliveries,
        } => {
            // Commit-before-publish (decision 5): Python committed both DBs before
            // emitting this frame, so the post-commit fan-out is published now —
            // independently of the driver's reply, exactly like `CommandReply`.
            for directive in &deliveries {
                relay_directive(ctx, directive);
            }
            let key = command_id.0.clone();
            let waiter = exec.lock().await.remove(&key);
            match waiter {
                Some(tx) => {
                    let _ = tx.send(GatewayOutbound::OutcomeApplied {
                        command_id,
                        direct_reply,
                        deliveries,
                    });
                }
                None => tracing::warn!(
                    command_id = %key,
                    "outcome-applied reply had no matching pending execution"
                ),
            }
        }
    }
}

/// Fan one directive into the shared registry and enforce backpressure: relay via
/// [`dispatch_with_config`] (using the operational threshold), log any non-silent
/// failures, and — for every recipient whose sustained overflow tripped the
/// slow-consumer threshold — fire its close signal through the
/// [`DisconnectHub`](crate::disconnect::DisconnectHub) so the owning writer task
/// closes the WebSocket with 1013 (Phase 3c, item 3). Each trigger is a
/// non-blocking `watch` send, so tearing one stalled consumer down never delays a
/// sibling's delivery.
fn relay_directive(
    ctx: &DispatchContext,
    directive: &lorecraft_protocol::gateway::DeliveryDirective,
) {
    let report = dispatch_with_config(&ctx.registry, directive, &ctx.backpressure);
    if !report.is_clean() {
        tracing::warn!(
            failures = report.failures.len(),
            "fan-out delivery had non-silent failures"
        );
    }
    for directive in &report.disconnect {
        tracing::info!(
            reason = directive.reason.as_str(),
            "slow consumer tripped disconnect threshold; signalling close"
        );
        ctx.disconnect.trigger(directive);
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
    use crate::disconnect::DisconnectHub;
    use lorecraft_events::{
        outbound_channel, BackpressureConfig, ConnectionRegistry, DEFAULT_OUTBOUND_QUEUE_DEPTH,
    };
    use lorecraft_protocol::gateway::{DeliveryDirective, DeliveryTarget, GatewayInbound};
    use lorecraft_protocol::ids::{ActorId, CommandId, PlayerId, SessionId, WorldId};
    use lorecraft_protocol::PROTOCOL_VERSION;
    use serde_json::json;
    use tokio::net::UnixListener;

    /// A dispatch context wrapping `registry` with a fresh hub + default threshold —
    /// the shape [`ForwardClient::connect`] now takes.
    fn ctx(registry: Arc<ConnectionRegistry>) -> DispatchContext {
        DispatchContext::new(
            registry,
            Arc::new(DisconnectHub::new()),
            BackpressureConfig::default(),
        )
    }

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
                    coalesce_key: None,
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

        let client = ForwardClient::connect(&socket_path, ctx(Arc::clone(&registry)))
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
            delivered.payload,
            json!({"type": "feed_append", "text": "someone looks around."})
        );

        peer.await.expect("mock peer joins cleanly");
    }

    /// THE GAP-1 REGISTRY PROOF: a `MovePlayer` frame relocates the mover in the
    /// shared registry so a *subsequent* room-targeted `Deliver` aimed at their
    /// **new** room reaches them. The mover starts registered in `old-room`; the
    /// mock peer sends `MovePlayer{old-room -> new-room}` then a `Deliver` to
    /// `new-room`. Assert the mover's outbound channel receives the new-room
    /// payload — which it only can if the move was applied first. Without the
    /// `MovePlayer` handler the registry would still place the mover in `old-room`
    /// and the delivery would never reach them.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn move_player_frame_relocates_mover_so_new_room_deliver_reaches_them() {
        let dir = tempfile::tempdir().expect("tempdir");
        let socket_path = dir.path().join("gateway.sock");
        let listener = UnixListener::bind(&socket_path).expect("bind mock peer");

        // The mover is registered in the OLD room, as they would be at connect.
        let registry = Arc::new(ConnectionRegistry::new());
        let (mover_tx, mut mover_rx) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        registry.register(PlayerId("mover".into()), mover_tx, Some("old-room".into()));
        // Sanity: the registry does not yet place the mover in the new room.
        assert!(registry.players_in_room("new-room").is_empty());

        let peer = tokio::spawn(async move {
            let (stream, _) = listener.accept().await.expect("accept");
            let (_read, mut write) = stream.into_split();
            // First the room move, THEN a broadcast to the new room — the order the
            // real adapter emits (move frame ahead of the command's deliveries).
            let move_frame = GatewayOutbound::MovePlayer {
                player_id: PlayerId("mover".into()),
                from_room: Some("old-room".into()),
                to_room: "new-room".into(),
            };
            write
                .write_all(&encode_frame(&move_frame))
                .await
                .expect("write move");
            let deliver = GatewayOutbound::Deliver {
                directive: DeliveryDirective {
                    target: DeliveryTarget::Room {
                        id: "new-room".into(),
                    },
                    exclude: None,
                    payload: json!({"type": "feed_append", "text": "a bell tolls in the new room."}),
                    coalesce_key: None,
                },
            };
            write
                .write_all(&encode_frame(&deliver))
                .await
                .expect("write deliver");
            write.flush().await.expect("flush");
            tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        });

        let client = ForwardClient::connect(&socket_path, ctx(Arc::clone(&registry)))
            .await
            .expect("connect");

        // The mover, now relocated by the MovePlayer frame, receives the new-room
        // broadcast on its outbound channel.
        let delivered = tokio::time::timeout(std::time::Duration::from_secs(2), mover_rx.recv())
            .await
            .expect("mover receives without stalling")
            .expect("a payload was delivered to the moved player");
        assert_eq!(
            delivered.payload,
            json!({"type": "feed_append", "text": "a bell tolls in the new room."})
        );

        // The registry now reflects the move on both sides of the map.
        assert_eq!(
            registry.players_in_room("new-room"),
            vec![PlayerId("mover".into())]
        );
        assert!(registry.players_in_room("old-room").is_empty());

        drop(client);
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
        let client = ForwardClient::connect(&socket_path, ctx(registry))
            .await
            .expect("connect");

        let result = client.send_command(sample_envelope("cmd-2", "look")).await;
        assert!(matches!(result, Err(ForwardError::ConnectionClosed)));

        peer.await.expect("mock peer joins cleanly");
    }

    /// The 3b control-handshake routing: a `RedeemTicket` is answered by the
    /// routed `AuthResult`, then (sequentially on the same link) a `Connected` is
    /// answered by the routed `ConnectAck` — no correlation id involved.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn sequential_control_handshakes_route_auth_result_then_connect_ack() {
        let dir = tempfile::tempdir().expect("tempdir");
        let socket_path = dir.path().join("gateway.sock");
        let listener = UnixListener::bind(&socket_path).expect("bind mock peer");

        let peer = tokio::spawn(async move {
            let (stream, _) = listener.accept().await.expect("accept");
            let (mut read, mut write) = stream.into_split();

            match read_inbound(&mut read).await {
                GatewayInbound::RedeemTicket { ticket } => assert_eq!(ticket, "tkt-1"),
                other => panic!("expected RedeemTicket, got {other:?}"),
            }
            let auth = GatewayOutbound::AuthResult {
                accepted: true,
                player_id: Some(PlayerId("player-9".into())),
            };
            write
                .write_all(&encode_frame(&auth))
                .await
                .expect("write auth");

            match read_inbound(&mut read).await {
                GatewayInbound::Connected { player_id } => {
                    assert_eq!(player_id, PlayerId("player-9".into()));
                }
                other => panic!("expected Connected, got {other:?}"),
            }
            let ack = GatewayOutbound::ConnectAck {
                session_id: SessionId("sess-9".into()),
                room_id: "tavern".into(),
                direct_frames: vec![json!({"type": "connected", "player_id": "player-9"})],
            };
            write
                .write_all(&encode_frame(&ack))
                .await
                .expect("write ack");
            write.flush().await.expect("flush");
            // Keep the link open so the client's read loop stays alive.
            tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        });

        let registry = Arc::new(ConnectionRegistry::new());
        let client = ForwardClient::connect(&socket_path, ctx(registry))
            .await
            .expect("connect");

        let decision = client.redeem_ticket("tkt-1").await.expect("redeem");
        assert_eq!(
            decision,
            AuthDecision {
                accepted: true,
                player_id: Some(PlayerId("player-9".into())),
            }
        );

        let ack = client
            .connect_session(PlayerId("player-9".into()))
            .await
            .expect("connect_session");
        assert_eq!(ack.session_id, SessionId("sess-9".into()));
        assert_eq!(ack.room_id, "tavern");
        assert_eq!(
            ack.direct_frames,
            vec![json!({"type": "connected", "player_id": "player-9"})]
        );

        peer.await.expect("mock peer joins cleanly");
    }

    /// THE DISCONNECT-FIX PROOF: the teardown fan-out reaches a *still-registered*
    /// sibling before `send_disconnected` returns. The mock peer replies to
    /// `Disconnected` with a room-targeted `player_left` `Deliver` **then** the
    /// terminal `DisconnectAck`. Assert (a) the sibling receives the `player_left`
    /// payload, and (b) `send_disconnected` resolves `Ok(())` — i.e. it awaited the
    /// ack and did not return (letting the link drop) before the fan-out landed.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn disconnect_awaits_ack_after_teardown_deliveries_reach_sibling() {
        let dir = tempfile::tempdir().expect("tempdir");
        let socket_path = dir.path().join("gateway.sock");
        let listener = UnixListener::bind(&socket_path).expect("bind mock peer");

        // A sibling still in the room the leaver was in.
        let registry = Arc::new(ConnectionRegistry::new());
        let (sibling_tx, mut sibling_rx) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        registry.register(
            PlayerId("sibling".into()),
            sibling_tx,
            Some("tavern".into()),
        );

        let peer = tokio::spawn(async move {
            let (stream, _) = listener.accept().await.expect("accept");
            let (mut read, mut write) = stream.into_split();
            match read_inbound(&mut read).await {
                GatewayInbound::Disconnected { player_id, .. } => {
                    assert_eq!(player_id, PlayerId("leaver".into()));
                }
                other => panic!("expected Disconnected, got {other:?}"),
            }
            // Teardown fan-out first, terminal ack last — the real adapter order.
            let leave = GatewayOutbound::Deliver {
                directive: DeliveryDirective {
                    target: DeliveryTarget::Room {
                        id: "tavern".into(),
                    },
                    exclude: None,
                    payload: json!({"type": "player_left", "player_id": "leaver"}),
                    coalesce_key: None,
                },
            };
            write
                .write_all(&encode_frame(&leave))
                .await
                .expect("write leave");
            write
                .write_all(&encode_frame(&GatewayOutbound::DisconnectAck))
                .await
                .expect("write ack");
            write.flush().await.expect("flush");
            tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        });

        let client = ForwardClient::connect(&socket_path, ctx(Arc::clone(&registry)))
            .await
            .expect("connect");

        client
            .send_disconnected(PlayerId("leaver".into()), DisconnectReason::ClientClose)
            .await
            .expect("disconnect completes on ack");

        // The sibling already has the leave payload queued once send returned.
        let delivered = sibling_rx
            .try_recv()
            .expect("player_left already delivered");
        assert_eq!(
            delivered.payload,
            json!({"type": "player_left", "player_id": "leaver"})
        );

        peer.await.expect("mock peer joins cleanly");
    }

    /// A peer that reads `Disconnected` then drops without ever sending
    /// `DisconnectAck` must fail `send_disconnected` with `ConnectionClosed`
    /// rather than hang it forever.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn disconnect_without_ack_fails_closed_not_hang() {
        let dir = tempfile::tempdir().expect("tempdir");
        let socket_path = dir.path().join("gateway.sock");
        let listener = UnixListener::bind(&socket_path).expect("bind mock peer");

        let peer = tokio::spawn(async move {
            let (stream, _) = listener.accept().await.expect("accept");
            let (mut read, write) = stream.into_split();
            let _ = read_inbound(&mut read).await; // read the Disconnected
            drop(write); // close without acking
            drop(read);
        });

        let registry = Arc::new(ConnectionRegistry::new());
        let client = ForwardClient::connect(&socket_path, ctx(registry))
            .await
            .expect("connect");

        let result = client
            .send_disconnected(PlayerId("leaver".into()), DisconnectReason::ClientClose)
            .await;
        assert!(matches!(result, Err(ForwardError::ConnectionClosed)));

        peer.await.expect("mock peer joins cleanly");
    }

    /// A dropped link mid-handshake fails the control waiter with
    /// `ConnectionClosed` rather than hanging it.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn dropped_connection_fails_pending_control_handshake() {
        let dir = tempfile::tempdir().expect("tempdir");
        let socket_path = dir.path().join("gateway.sock");
        let listener = UnixListener::bind(&socket_path).expect("bind mock peer");

        let peer = tokio::spawn(async move {
            let (stream, _) = listener.accept().await.expect("accept");
            let (mut read, write) = stream.into_split();
            let _ = read_inbound(&mut read).await; // read the RedeemTicket
            drop(write); // close without answering
            drop(read);
        });

        let registry = Arc::new(ConnectionRegistry::new());
        let client = ForwardClient::connect(&socket_path, ctx(registry))
            .await
            .expect("connect");

        let result = client.redeem_ticket("tkt-x").await;
        assert!(matches!(result, Err(ForwardError::ConnectionClosed)));

        peer.await.expect("mock peer joins cleanly");
    }
}
