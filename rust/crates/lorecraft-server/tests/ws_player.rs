//! Hermetic integration tests for the Phase 3b player `/ws` cutover.
//!
//! A mock UDS peer (a [`UnixListener`] speaking the length-prefixed-JSON gateway
//! protocol, exactly like the Python adapter) stands in for
//! `src/lorecraft/gateway/adapter.py`, and a real WebSocket client
//! (`tokio-tungstenite`) drives the real Axum router — proving the full
//! Rust-side path: upgrade → ticket handoff → connect handshake → registered
//! writer task → command forward → fan-out dispatch → disconnect notify.

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use lorecraft_server::lorecraft_events::{
    outbound_channel, ConnectionRegistry, RateLimitConfig, DEFAULT_OUTBOUND_QUEUE_DEPTH,
};
use lorecraft_server::lorecraft_protocol::gateway::{
    DeliveryDirective, DeliveryTarget, DisconnectReason, GatewayInbound, GatewayOutbound,
};
use lorecraft_server::lorecraft_protocol::ids::{PlayerId, SessionId};
use lorecraft_server::{
    build_router, DisconnectHub, DispatchContext, ForwardClient, GatewayConfig,
};
use serde_json::{json, Value};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::unix::{OwnedReadHalf, OwnedWriteHalf};
use tokio::net::{TcpListener, TcpStream, UnixListener, UnixStream};
use tokio::sync::mpsc;
use tokio::time::timeout;
use tokio_tungstenite::tungstenite::Message as WsMessage;
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream};

const LENGTH_PREFIX_BYTES: usize = 4;
const STEP: Duration = Duration::from_secs(3);

type WsClient = WebSocketStream<MaybeTlsStream<TcpStream>>;

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

// ---------------------------------------------------------------------------
// Mock Python adapter: serves EVERY accepted UDS connection (the per-player
// links plus the gateway's shared health-check link) against one ticket table.
// ---------------------------------------------------------------------------

fn spawn_mock_adapter(
    listener: UnixListener,
    tickets: HashMap<String, String>,
) -> mpsc::UnboundedReceiver<GatewayInbound> {
    let (events_tx, events_rx) = mpsc::unbounded_channel();
    tokio::spawn(async move {
        while let Ok((stream, _)) = listener.accept().await {
            tokio::spawn(serve_connection(stream, tickets.clone(), events_tx.clone()));
        }
    });
    events_rx
}

async fn serve_connection(
    stream: UnixStream,
    tickets: HashMap<String, String>,
    events: mpsc::UnboundedSender<GatewayInbound>,
) {
    let (mut read, mut write) = stream.into_split();
    while let Some(inbound) = read_inbound(&mut read).await {
        let _ = events.send(inbound.clone());
        let replies: Vec<GatewayOutbound> = match inbound {
            GatewayInbound::RedeemTicket { ticket } => {
                let player = tickets.get(&ticket).cloned();
                vec![GatewayOutbound::AuthResult {
                    accepted: player.is_some(),
                    player_id: player.map(PlayerId),
                }]
            }
            GatewayInbound::Connected { player_id } => vec![GatewayOutbound::ConnectAck {
                session_id: SessionId(format!("sess-{}", player_id.0)),
                room_id: "tavern".to_owned(),
                direct_frames: vec![json!({
                    "type": "connected",
                    "player_id": player_id.0,
                    "room_id": "tavern",
                })],
            }],
            GatewayInbound::Command(env) => {
                // `wave` produces a room-targeted side-effect delivery excluding
                // the actor, mirroring a third-person broadcast.
                let deliveries = if env.raw == "wave" {
                    vec![DeliveryDirective {
                        target: DeliveryTarget::Room {
                            id: "tavern".to_owned(),
                        },
                        exclude: Some(env.player_id.clone()),
                        payload: json!({"type": "feed_append", "text": "someone waves."}),
                        coalesce_key: None,
                    }]
                } else {
                    vec![]
                };
                vec![GatewayOutbound::CommandReply {
                    command_id: env.command_id,
                    direct_reply: json!({"command": env.raw, "messages": ["ok"]}),
                    deliveries,
                }]
            }
            // Mirror the Python adapter's teardown-response path: a `Disconnected`
            // yields the leave fan-out (`player_left` to the room) FOLLOWED BY the
            // terminal `DisconnectAck`. Returning `vec![]` here is exactly what hid
            // the disconnect bug — the leave was never exercised through Rust.
            GatewayInbound::Disconnected { player_id, .. } => vec![
                GatewayOutbound::Deliver {
                    directive: DeliveryDirective {
                        target: DeliveryTarget::Room {
                            id: "tavern".to_owned(),
                        },
                        exclude: None,
                        payload: json!({"type": "player_left", "player_id": player_id.0}),
                        coalesce_key: None,
                    },
                },
                GatewayOutbound::DisconnectAck,
            ],
            GatewayInbound::ValidateAdminToken { .. } => vec![GatewayOutbound::AuthResult {
                accepted: false,
                player_id: None,
            }],
            // TODO(4a-task3): the Phase 4 execution round-trip is not exercised by
            // this Phase 3 forwarding mock; the real `BuildSnapshot`/`ApplyOutcome`
            // handling is wired when the Rust execution router lands.
            GatewayInbound::BuildSnapshot { .. } | GatewayInbound::ApplyOutcome { .. } => vec![],
        };
        for frame in &replies {
            write_outbound(&mut write, frame).await;
        }
    }
}

// ---------------------------------------------------------------------------
// Gateway harness
// ---------------------------------------------------------------------------

struct Harness {
    addr: SocketAddr,
    registry: Arc<ConnectionRegistry>,
    events: mpsc::UnboundedReceiver<GatewayInbound>,
    _socket_dir: tempfile::TempDir,
}

async fn start_gateway(tickets: &[(&str, &str)]) -> Harness {
    start_gateway_cfg(tickets, |_| {}).await
}

async fn start_gateway_cfg(
    tickets: &[(&str, &str)],
    tweak: impl FnOnce(&mut GatewayConfig),
) -> Harness {
    let socket_dir = tempfile::tempdir().expect("tempdir");
    let socket_path = socket_dir.path().join("gateway.sock");
    let listener = UnixListener::bind(&socket_path).expect("bind mock adapter");
    let tickets: HashMap<String, String> = tickets
        .iter()
        .map(|(t, p)| ((*t).to_owned(), (*p).to_owned()))
        .collect();
    let events = spawn_mock_adapter(listener, tickets);

    let registry = Arc::new(ConnectionRegistry::new());
    let disconnect = Arc::new(DisconnectHub::new());
    let mut config = GatewayConfig {
        socket_path: socket_path.clone(),
        handshake_timeout_ms: 2_000,
        ..GatewayConfig::default()
    };
    tweak(&mut config);
    let config = Arc::new(config);
    let ctx = DispatchContext::new(
        Arc::clone(&registry),
        Arc::clone(&disconnect),
        config.backpressure,
    );
    let forward = Arc::new(
        ForwardClient::connect(&socket_path, ctx)
            .await
            .expect("shared forward link connects"),
    );
    let router = build_router(config, Arc::clone(&registry), forward, disconnect);

    let tcp = TcpListener::bind("127.0.0.1:0").await.expect("bind :0");
    let addr = tcp.local_addr().expect("local addr");
    tokio::spawn(async move {
        axum::serve(tcp, router).await.expect("gateway serves");
    });

    Harness {
        addr,
        registry,
        events,
        _socket_dir: socket_dir,
    }
}

async fn ws_connect(addr: SocketAddr, ticket: &str) -> WsClient {
    let (ws, _response) =
        tokio_tungstenite::connect_async(format!("ws://{addr}/ws?ticket={ticket}"))
            .await
            .expect("websocket upgrade");
    ws
}

/// Next **text** frame from the client socket, decoded as JSON.
async fn next_text(ws: &mut WsClient) -> Value {
    loop {
        let msg = timeout(STEP, ws.next())
            .await
            .expect("frame arrives in time")
            .expect("stream still open")
            .expect("frame decodes");
        match msg {
            WsMessage::Text(text) => return serde_json::from_str(&text).expect("frame is JSON"),
            WsMessage::Close(frame) => panic!("unexpected close: {frame:?}"),
            _ => {} // ping/pong noise
        }
    }
}

/// Await the server-initiated close, returning `(code, reason)`.
async fn next_close(ws: &mut WsClient) -> (u16, String) {
    loop {
        let msg = timeout(STEP, ws.next())
            .await
            .expect("close arrives in time")
            .expect("stream still open")
            .expect("frame decodes");
        if let WsMessage::Close(frame) = msg {
            let frame = frame.expect("close carries a code + reason");
            return (frame.code.into(), frame.reason.to_string());
        }
    }
}

/// Drain mock-adapter events until one matches `pick`, within the step budget.
async fn await_event<T>(
    events: &mut mpsc::UnboundedReceiver<GatewayInbound>,
    mut pick: impl FnMut(&GatewayInbound) -> Option<T>,
) -> T {
    let deadline = tokio::time::Instant::now() + STEP;
    loop {
        let remaining = deadline.saturating_duration_since(tokio::time::Instant::now());
        let event = timeout(remaining, events.recv())
            .await
            .expect("expected adapter event in time")
            .expect("event channel open");
        if let Some(found) = pick(&event) {
            return found;
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

/// THE HAPPY PATH: ticket redeemed, connect handshake acked, the `connected`
/// direct frame reaches the client, a `look` round-trips to its `direct_reply`,
/// and closing the socket notifies Python with `Disconnected{ClientClose}` and
/// drops the registry entry.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn happy_path_connect_command_and_disconnect() {
    let mut harness = start_gateway(&[("good-ticket", "hero")]).await;
    let mut ws = ws_connect(harness.addr, "good-ticket").await;

    // The ConnectAck's direct frame arrives first, as a text frame.
    let connected = next_text(&mut ws).await;
    assert_eq!(connected["type"], json!("connected"));
    assert_eq!(connected["player_id"], json!("hero"));
    assert_eq!(connected["room_id"], json!("tavern"));

    // The player is registered in the shared connection map, in its room.
    let hero = PlayerId("hero".to_owned());
    assert!(harness.registry.is_connected(&hero));
    assert_eq!(
        harness.registry.players_in_room("tavern"),
        vec![hero.clone()]
    );

    // A command round-trips: raw text in, opaque direct_reply out.
    ws.send(WsMessage::text("look")).await.expect("send look");
    let reply = next_text(&mut ws).await;
    assert_eq!(reply, json!({"command": "look", "messages": ["ok"]}));

    // The forwarded envelope carried the authenticated identity + session.
    let envelope = await_event(&mut harness.events, |event| match event {
        GatewayInbound::Command(env) if env.raw == "look" => Some(env.clone()),
        _ => None,
    })
    .await;
    assert_eq!(envelope.player_id, hero);
    assert_eq!(envelope.actor_id.0, "hero");
    assert_eq!(envelope.session_id, SessionId("sess-hero".to_owned()));
    assert_eq!(envelope.receive_sequence, 1);
    assert!(!envelope.command_id.0.is_empty());

    // Client-initiated close → Python is told, with ClientClose.
    ws.close(None).await.expect("client close");
    let reason = await_event(&mut harness.events, |event| match event {
        GatewayInbound::Disconnected { player_id, reason } if *player_id == hero => {
            Some(reason.clone())
        }
        _ => None,
    })
    .await;
    assert_eq!(reason, DisconnectReason::ClientClose);

    // The registry entry is gone once teardown completes.
    let deadline = tokio::time::Instant::now() + STEP;
    while harness.registry.is_connected(&hero) {
        assert!(
            tokio::time::Instant::now() < deadline,
            "registry entry should be deregistered after close"
        );
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
}

/// EXIT-CHECK REQUIREMENT: a bad/expired ticket yields WS close **1008**
/// through Rust, with the same reason string as the Python endpoint.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn bad_ticket_closes_1008() {
    let harness = start_gateway(&[("good-ticket", "hero")]).await;
    let mut ws = ws_connect(harness.addr, "expired-ticket").await;

    let (code, reason) = next_close(&mut ws).await;
    assert_eq!(code, 1008);
    assert_eq!(reason, "Invalid or expired ticket");
    assert!(!harness.registry.is_connected(&PlayerId("hero".to_owned())));
}

/// Single-live-connection rule (main.py ~466-483): a second tab for an
/// already-connected player is rejected 1008/`already_connected`, and the first
/// connection keeps working.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn second_connection_for_same_player_closes_1008_already_connected() {
    let harness = start_gateway(&[("ticket-a", "hero"), ("ticket-b", "hero")]).await;

    let mut first = ws_connect(harness.addr, "ticket-a").await;
    let connected = next_text(&mut first).await;
    assert_eq!(connected["type"], json!("connected"));

    let mut second = ws_connect(harness.addr, "ticket-b").await;
    let (code, reason) = next_close(&mut second).await;
    assert_eq!(code, 1008);
    assert_eq!(reason, "already_connected");

    // The first tab is unaffected.
    first
        .send(WsMessage::text("look"))
        .await
        .expect("send look");
    let reply = next_text(&mut first).await;
    assert_eq!(reply["command"], json!("look"));
}

/// THE DISCONNECT REGRESSION GUARD: when a gateway-fronted player's WS drops, the
/// teardown `player_left` fan-out must reach a still-connected room sibling. This
/// exercises the full path — WS close → `Disconnected` down the dying link →
/// Python's leave `Deliver` read + dispatched into the shared registry → sibling's
/// outbound queue — *before* the link is torn down. Before the fix, Rust aborted
/// the link's read loop microseconds after writing `Disconnected`, so this
/// `player_left` never arrived and the assertion below would time out.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn disconnect_fans_out_player_left_to_room_sibling() {
    let harness = start_gateway(&[("ticket-a", "leaver")]).await;

    // A sibling registered directly in the shared registry, in the same room the
    // mock adapter places connecting players into.
    let (sibling_tx, mut sibling_rx) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
    harness.registry.register(
        PlayerId("bystander".to_owned()),
        sibling_tx,
        Some("tavern".to_owned()),
    );

    let mut ws = ws_connect(harness.addr, "ticket-a").await;
    let connected = next_text(&mut ws).await;
    assert_eq!(connected["player_id"], json!("leaver"));
    assert!(harness
        .registry
        .is_connected(&PlayerId("leaver".to_owned())));

    // The player drops: close the socket.
    ws.close(None).await.expect("client close");

    // The sibling's queue receives the leave broadcast produced by the teardown.
    let delivered = timeout(STEP, sibling_rx.recv())
        .await
        .expect("player_left reaches the sibling before teardown drops the link")
        .expect("sibling channel open");
    assert_eq!(
        delivered.payload,
        json!({"type": "player_left", "player_id": "leaver"})
    );
}

/// Fan-out: a `CommandReply.deliveries` room directive produced on the acting
/// player's link lands on a co-located *registered* sibling's outbound queue
/// (registry-level assertion, mirroring 3a's forward test approach), while the
/// excluded actor receives only the direct reply.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn command_deliveries_fan_out_to_room_sibling() {
    let harness = start_gateway(&[("ticket-a", "actor")]).await;

    // A sibling recipient registered directly in the shared registry, in the
    // same room the mock adapter places connecting players into.
    let (sibling_tx, mut sibling_rx) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
    harness.registry.register(
        PlayerId("bystander".to_owned()),
        sibling_tx,
        Some("tavern".to_owned()),
    );

    let mut ws = ws_connect(harness.addr, "ticket-a").await;
    let connected = next_text(&mut ws).await;
    assert_eq!(connected["player_id"], json!("actor"));

    ws.send(WsMessage::text("wave")).await.expect("send wave");

    // The actor gets exactly the direct reply (the room broadcast excludes it).
    let reply = next_text(&mut ws).await;
    assert_eq!(reply, json!({"command": "wave", "messages": ["ok"]}));

    // The sibling's queue received the broadcast payload.
    let delivered = timeout(STEP, sibling_rx.recv())
        .await
        .expect("sibling delivery arrives in time")
        .expect("sibling channel open");
    assert_eq!(
        delivered.payload,
        json!({"type": "feed_append", "text": "someone waves."})
    );
}

/// Per-player command RATE LIMIT (Phase 3c, item 5): with a deliberately tiny
/// burst (2, no refill), a client that floods commands has its first `burst`
/// admitted (real command replies) and every excess command rejected in-band with
/// a `rate_limited` error frame — the connection stays open, and at-most-one-
/// outstanding is preserved (each reply is awaited before the next read). The
/// generous production default means a well-behaved client never reaches this.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn command_rate_limit_throttles_a_flood_but_keeps_the_connection() {
    let harness = start_gateway_cfg(&[("ticket-a", "hero")], |cfg| {
        // Tiny bucket, no refill during the test → deterministic throttling.
        cfg.rate_limit = RateLimitConfig {
            burst: 2,
            per_second: 0.0,
        };
    })
    .await;

    let mut ws = ws_connect(harness.addr, "ticket-a").await;
    let connected = next_text(&mut ws).await;
    assert_eq!(connected["type"], json!("connected"));

    // Flood five commands back to back.
    for _ in 0..5 {
        ws.send(WsMessage::text("look")).await.expect("send look");
    }

    // The first two are admitted (real command replies); the next three are
    // rejected in-band with a rate_limited error frame — five ordered outbound
    // frames total, connection still open.
    let mut admitted = 0;
    let mut throttled = 0;
    for _ in 0..5 {
        let frame = next_text(&mut ws).await;
        if frame["type"] == json!("error") {
            assert_eq!(frame["code"], json!("rate_limited"));
            throttled += 1;
        } else {
            assert_eq!(frame["command"], json!("look"));
            admitted += 1;
        }
    }
    assert_eq!(admitted, 2, "exactly the burst was admitted");
    assert_eq!(throttled, 3, "every excess command was throttled in-band");

    // The connection is unharmed by throttling — it is still live in the registry.
    assert!(harness.registry.is_connected(&PlayerId("hero".to_owned())));
}
