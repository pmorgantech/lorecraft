//! Hermetic integration test for the Phase 4 Rust execution driver (sub-slice 4a).
//!
//! A mock UDS peer (a [`UnixListener`] speaking the length-prefixed-JSON gateway
//! protocol, exactly like `src/lorecraft/gateway/adapter.py`) stands in for the
//! Python adapter. It answers the Option-A round-trip:
//!
//! - on [`GatewayInbound::BuildSnapshot`] it replies [`GatewayOutbound::SnapshotReady`]
//!   carrying the real `look_only` fixture [`ScriptRequest`], and
//! - on [`GatewayInbound::ApplyOutcome`] it replies [`GatewayOutbound::OutcomeApplied`]
//!   with an opaque `direct_reply` and one room-targeted delivery.
//!
//! We drive a `look` [`CommandEnvelope`] through [`execute::execute`] against a real
//! [`ForwardClient`] and assert the full seam: the driver sent `BuildSnapshot` then
//! `ApplyOutcome` (with a read-only [`CommandOutcome`] whose messages came from
//! [`lorecraft_feature_look`]), returned the mock's `direct_reply`, and the
//! post-commit deliveries were fanned out into the [`ConnectionRegistry`].
//!
//! There is **no live client cutover** here (that is 4b): the driver is exercised
//! directly, proving the seam before any real `/ws` command is routed to it.

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use lorecraft_server::lorecraft_events::{
    outbound_channel, BackpressureConfig, ConnectionRegistry, DEFAULT_OUTBOUND_QUEUE_DEPTH,
};
use lorecraft_server::lorecraft_feature_look::look_effects;
use lorecraft_server::lorecraft_protocol::envelope::{CommandEnvelope, OutcomeStatus};
use lorecraft_server::lorecraft_protocol::gateway::{
    DeliveryDirective, DeliveryTarget, GatewayInbound, GatewayOutbound,
};
use lorecraft_server::lorecraft_protocol::ids::{ActorId, CommandId, PlayerId, SessionId, WorldId};
use lorecraft_server::lorecraft_protocol::script::ScriptRequest;
use lorecraft_server::lorecraft_protocol::PROTOCOL_VERSION;
use lorecraft_server::{execute, route, DisconnectHub, DispatchContext, ForwardClient};
use serde_json::json;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::unix::{OwnedReadHalf, OwnedWriteHalf};
use tokio::net::UnixListener;
use tokio::sync::mpsc;
use tokio::time::timeout;

const LENGTH_PREFIX_BYTES: usize = 4;
const STEP: Duration = Duration::from_secs(3);

// ---------------------------------------------------------------------------
// Framed-protocol helpers (mock-peer side of the UDS link)
// ---------------------------------------------------------------------------

async fn read_inbound(read: &mut OwnedReadHalf) -> Option<GatewayInbound> {
    let mut header = [0u8; LENGTH_PREFIX_BYTES];
    match read.read_exact(&mut header).await {
        Ok(_) => {}
        Err(err) if err.kind() == std::io::ErrorKind::UnexpectedEof => return None,
        Err(err) => panic!("mock peer header read failed: {err}"),
    }
    let len = u32::from_be_bytes(header) as usize;
    let mut body = vec![0u8; len];
    read.read_exact(&mut body)
        .await
        .expect("mock peer body read");
    Some(serde_json::from_slice(&body).expect("mock peer decodes GatewayInbound"))
}

async fn write_outbound(write: &mut OwnedWriteHalf, frame: &GatewayOutbound) {
    let body = serde_json::to_vec(frame).expect("mock peer encodes GatewayOutbound");
    let len = u32::try_from(body.len()).expect("frame fits u32");
    write
        .write_all(&len.to_be_bytes())
        .await
        .expect("mock peer writes header");
    write.write_all(&body).await.expect("mock peer writes body");
    write.flush().await.expect("mock peer flushes");
}

/// Load the shared `look_only` fixture request (`rust/fixtures/look_only`).
fn fixture_request() -> ScriptRequest {
    let path = PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../fixtures/look_only/request.json"
    ));
    let text = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("read fixture {}: {e}", path.display()));
    serde_json::from_str(&text).expect("fixture is a ScriptRequest")
}

fn look_envelope(command_id: &str) -> CommandEnvelope {
    CommandEnvelope {
        protocol_version: PROTOCOL_VERSION,
        world_id: WorldId("world-1".into()),
        actor_id: ActorId("player-1".into()),
        player_id: PlayerId("player-1".into()),
        session_id: SessionId("session-1".into()),
        command_id: CommandId(command_id.into()),
        receive_sequence: 1,
        deadline_ms: 5_000,
        raw: "look".into(),
    }
}

fn ctx(registry: Arc<ConnectionRegistry>) -> DispatchContext {
    DispatchContext::new(
        registry,
        Arc::new(DisconnectHub::new()),
        BackpressureConfig::default(),
    )
}

/// THE 4a EXECUTION-SEAM PROOF: drive `look` through the Rust driver against a
/// mock Python peer and assert the whole Option-A round-trip.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn look_driver_runs_option_a_round_trip_and_fans_out_deliveries() {
    let dir = tempfile::tempdir().expect("tempdir");
    let socket_path = dir.path().join("gateway.sock");
    let listener = UnixListener::bind(&socket_path).expect("bind mock peer");

    // A recipient pre-registered in the room the OutcomeApplied delivery targets.
    let registry = Arc::new(ConnectionRegistry::new());
    let (recipient_tx, mut recipient_rx) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
    registry.register(
        PlayerId("bystander".into()),
        recipient_tx,
        Some("village_square".into()),
    );

    let direct_reply_body = json!({"command": "look", "messages": ["you look around"]});
    let delivery_payload = json!({"type": "state_change", "room_id": "village_square"});

    // Mock Python adapter: BuildSnapshot -> SnapshotReady(fixture);
    // ApplyOutcome -> OutcomeApplied(direct_reply + one room delivery). It streams
    // every inbound frame back to the test so we can assert order + contents.
    let (events_tx, mut events_rx) = mpsc::unbounded_channel::<GatewayInbound>();
    let reply = direct_reply_body.clone();
    let payload = delivery_payload.clone();
    let peer = tokio::spawn(async move {
        let (stream, _) = listener.accept().await.expect("accept");
        let (mut read, mut write) = stream.into_split();
        while let Some(inbound) = read_inbound(&mut read).await {
            let _ = events_tx.send(inbound.clone());
            match inbound {
                GatewayInbound::BuildSnapshot { envelope } => {
                    write_outbound(
                        &mut write,
                        &GatewayOutbound::SnapshotReady {
                            command_id: envelope.command_id,
                            request: Box::new(fixture_request()),
                        },
                    )
                    .await;
                }
                GatewayInbound::ApplyOutcome { command_id, .. } => {
                    write_outbound(
                        &mut write,
                        &GatewayOutbound::OutcomeApplied {
                            command_id,
                            direct_reply: reply.clone(),
                            deliveries: vec![DeliveryDirective {
                                target: DeliveryTarget::Room {
                                    id: "village_square".into(),
                                },
                                exclude: None,
                                payload: payload.clone(),
                                coalesce_key: None,
                            }],
                            moves: vec![],
                        },
                    )
                    .await;
                }
                other => panic!("unexpected inbound frame: {other:?}"),
            }
        }
    });

    let forward = ForwardClient::connect(&socket_path, ctx(Arc::clone(&registry)))
        .await
        .expect("connect");

    // Sanity: with `look` allow-listed the router chooses the Rust path.
    let allow: std::collections::HashSet<String> = route::parse_allow_list("look");
    assert_eq!(
        route::decide("look", &allow),
        route::RouteDecision::RustExecute(route::MigratedVerb::Look)
    );

    // Drive the driver.
    let returned = timeout(
        STEP,
        execute::execute(&forward, route::MigratedVerb::Look, look_envelope("cmd-1")),
    )
    .await
    .expect("driver completes in time")
    .expect("driver succeeds");

    // (ii) The driver returned the mock's opaque direct_reply verbatim.
    assert_eq!(returned, direct_reply_body);

    // (i) The driver sent BuildSnapshot THEN ApplyOutcome, correlated by command_id,
    // and the ApplyOutcome carried a read-only outcome whose messages came from the
    // feature run on the fixture request.
    let first = events_rx.recv().await.expect("first inbound");
    match first {
        GatewayInbound::BuildSnapshot { envelope } => {
            assert_eq!(envelope.command_id, CommandId("cmd-1".into()));
            assert_eq!(envelope.raw, "look");
        }
        other => panic!("expected BuildSnapshot first, got {other:?}"),
    }
    let second = events_rx.recv().await.expect("second inbound");
    match second {
        GatewayInbound::ApplyOutcome {
            command_id,
            outcome,
        } => {
            assert_eq!(command_id, CommandId("cmd-1".into()));
            assert_eq!(outcome.command_id, CommandId("cmd-1".into()));
            assert_eq!(outcome.status, OutcomeStatus::Executed);
            assert_eq!(outcome.commit_sequence, None);
            // Read-only verb: no effects to persist.
            assert!(
                outcome.applied_effects.is_empty(),
                "look derives no effects"
            );
            // Messages are exactly what the feature produces on the fixture request.
            let expected = look_effects(&fixture_request()).messages;
            assert_eq!(outcome.messages, expected);
            assert!(!outcome.messages.is_empty(), "look emits feed + panel");
        }
        other => panic!("expected ApplyOutcome second, got {other:?}"),
    }

    // (iii) The post-commit delivery was fanned out into the registry: the
    // pre-registered bystander received the payload on its outbound channel.
    let delivered = timeout(STEP, recipient_rx.recv())
        .await
        .expect("bystander receives without stalling")
        .expect("a payload was delivered");
    assert_eq!(delivered.payload, delivery_payload);

    drop(forward);
    peer.await.expect("mock peer joins cleanly");
}

/// FINDING #1/#2 SHORT-CIRCUIT PROOF: when the mock peer answers `BuildSnapshot`
/// with an `ExecutionRejected` (a frozen session, or a raised persistence handler),
/// the driver returns the carried client reply and sends **no** `ApplyOutcome` —
/// no feature outcome is persisted, nothing is broadcast. This is the seam that
/// keeps a raised Python handler or a frozen session from wedging the connection.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn look_driver_short_circuits_on_execution_rejected_and_sends_no_apply_outcome() {
    let dir = tempfile::tempdir().expect("tempdir");
    let socket_path = dir.path().join("gateway.sock");
    let listener = UnixListener::bind(&socket_path).expect("bind mock peer");

    let frozen_reply = json!({
        "type": "system",
        "text": "Your session is frozen. Contact an administrator.",
    });

    let (events_tx, mut events_rx) = mpsc::unbounded_channel::<GatewayInbound>();
    let rejection = frozen_reply.clone();
    let peer = tokio::spawn(async move {
        let (stream, _) = listener.accept().await.expect("accept");
        let (mut read, mut write) = stream.into_split();
        while let Some(inbound) = read_inbound(&mut read).await {
            let _ = events_tx.send(inbound.clone());
            match inbound {
                GatewayInbound::BuildSnapshot { envelope } => {
                    write_outbound(
                        &mut write,
                        &GatewayOutbound::ExecutionRejected {
                            command_id: envelope.command_id,
                            direct_reply: rejection.clone(),
                        },
                    )
                    .await;
                }
                // The driver must NOT reach the persistence leg on a rejection.
                GatewayInbound::ApplyOutcome { .. } => {
                    panic!("driver sent ApplyOutcome after an ExecutionRejected")
                }
                other => panic!("unexpected inbound frame: {other:?}"),
            }
        }
    });

    let registry = Arc::new(ConnectionRegistry::new());
    let forward = ForwardClient::connect(&socket_path, ctx(Arc::clone(&registry)))
        .await
        .expect("connect");

    let returned = timeout(
        STEP,
        execute::execute(
            &forward,
            route::MigratedVerb::Look,
            look_envelope("cmd-frozen"),
        ),
    )
    .await
    .expect("driver completes in time")
    .expect("driver succeeds with the rejection reply");

    // The client gets the frozen reply verbatim — a clean in-game message, no hang.
    assert_eq!(returned, frozen_reply);

    // Exactly one inbound frame (the BuildSnapshot); no ApplyOutcome followed.
    let first = events_rx.recv().await.expect("first inbound");
    assert!(
        matches!(first, GatewayInbound::BuildSnapshot { .. }),
        "expected BuildSnapshot, got {first:?}"
    );
    assert!(
        timeout(Duration::from_millis(300), events_rx.recv())
            .await
            .is_err(),
        "no second inbound frame — the round-trip short-circuited"
    );

    drop(forward);
    peer.await.expect("mock peer joins cleanly");
}

/// FINDING #1 TIMEOUT-BACKSTOP PROOF: a Python peer that answers **nothing** on the
/// snapshot leg must not wedge the connection. The caller wraps the driver in a
/// bounded `tokio::time::timeout`; on expiry it cleans up the pending slot via
/// `cancel_exec` (no leak) and the SAME link stays usable — a subsequent command
/// completes its full round-trip.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn mute_peer_times_out_then_link_stays_usable_for_next_command() {
    let dir = tempfile::tempdir().expect("tempdir");
    let socket_path = dir.path().join("gateway.sock");
    let listener = UnixListener::bind(&socket_path).expect("bind mock peer");

    let direct_reply_body = json!({"command": "look", "messages": ["you look around"]});
    let reply = direct_reply_body.clone();

    // Peer: swallow the FIRST inbound frame (the mute/timeout command), then serve
    // every subsequent frame's round-trip normally.
    let peer = tokio::spawn(async move {
        let (stream, _) = listener.accept().await.expect("accept");
        let (mut read, mut write) = stream.into_split();
        let mut seen = 0u32;
        while let Some(inbound) = read_inbound(&mut read).await {
            seen += 1;
            if seen == 1 {
                // Mute: read it, reply with nothing (the wedge scenario).
                continue;
            }
            match inbound {
                GatewayInbound::BuildSnapshot { envelope } => {
                    write_outbound(
                        &mut write,
                        &GatewayOutbound::SnapshotReady {
                            command_id: envelope.command_id,
                            request: Box::new(fixture_request()),
                        },
                    )
                    .await;
                }
                GatewayInbound::ApplyOutcome { command_id, .. } => {
                    write_outbound(
                        &mut write,
                        &GatewayOutbound::OutcomeApplied {
                            command_id,
                            direct_reply: reply.clone(),
                            deliveries: vec![],
                            moves: vec![],
                        },
                    )
                    .await;
                }
                other => panic!("unexpected inbound frame: {other:?}"),
            }
        }
    });

    let registry = Arc::new(ConnectionRegistry::new());
    let forward = ForwardClient::connect(&socket_path, ctx(Arc::clone(&registry)))
        .await
        .expect("connect");

    // 1st command: the peer is mute, so the bounded timeout fires. Then clean up the
    // pending slot exactly as `ws_player` does on the timeout path.
    let mute = look_envelope("cmd-mute");
    let mute_id = mute.command_id.clone();
    let timed_out = timeout(
        Duration::from_millis(300),
        execute::execute(&forward, route::MigratedVerb::Look, mute),
    )
    .await;
    assert!(
        timed_out.is_err(),
        "the mute leg must time out, not resolve"
    );
    forward.cancel_exec(&mute_id).await;

    // 2nd command on the SAME link completes its full round-trip — the connection
    // was never wedged by the timed-out command.
    let returned = timeout(
        STEP,
        execute::execute(&forward, route::MigratedVerb::Look, look_envelope("cmd-ok")),
    )
    .await
    .expect("second command completes in time")
    .expect("second command succeeds");
    assert_eq!(returned, direct_reply_body);

    drop(forward);
    peer.await.expect("mock peer joins cleanly");
}
