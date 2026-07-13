//! Hermetic integration tests for the Phase 3c admin `/admin/ws` cutover and the
//! slow-client backpressure enforcement.
//!
//! A mock UDS peer (a [`UnixListener`] speaking the length-prefixed-JSON gateway
//! protocol, exactly like the Python adapter) stands in for
//! `src/lorecraft/gateway/adapter.py`. It answers `ValidateAdminToken` with the
//! shape-distinct `AdminAuthResult`, and lets the test push `Deliver { Admin }`
//! frames down an admin link on demand (Python's `AdminBroadcaster.push`
//! equivalent). Real WebSocket clients (`tokio-tungstenite`) drive the real Axum
//! router, proving the full Rust-side path: accept-before-validate → 1008 on reject,
//! admin registration → push fan-out, and the slow-consumer 1013 disconnect that
//! leaves a co-located client unaffected.

use std::collections::HashSet;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use futures_util::StreamExt;
use lorecraft_server::lorecraft_events::{BackpressureConfig, ConnectionRegistry};
use lorecraft_server::lorecraft_protocol::gateway::{
    DeliveryDirective, DeliveryTarget, GatewayInbound, GatewayOutbound,
};
use lorecraft_server::{
    build_router, DisconnectHub, DispatchContext, ForwardClient, GatewayConfig,
};
use serde_json::{json, Value};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::unix::{OwnedReadHalf, OwnedWriteHalf};
use tokio::net::{TcpSocket, TcpStream, UnixListener, UnixStream};
use tokio::sync::Mutex;
use tokio::time::timeout;
use tokio_tungstenite::tungstenite::Message as WsMessage;
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream};

const LENGTH_PREFIX_BYTES: usize = 4;
const STEP: Duration = Duration::from_secs(5);

type WsClient = WebSocketStream<MaybeTlsStream<TcpStream>>;
/// The mock side of the admin push link: the write half of the first authenticated
/// admin's UDS connection, which the test writes `Deliver { Admin }` frames into.
type PushLink = Arc<Mutex<Option<OwnedWriteHalf>>>;

// ---------------------------------------------------------------------------
// Framed-protocol helpers (mock-peer side of the UDS link)
// ---------------------------------------------------------------------------

async fn read_inbound(read: &mut OwnedReadHalf) -> Option<GatewayInbound> {
    let mut header = [0u8; LENGTH_PREFIX_BYTES];
    match read.read_exact(&mut header).await {
        Ok(_) => {}
        Err(err) if err.kind() == std::io::ErrorKind::UnexpectedEof => return None,
        Err(_) => return None,
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
// Mock Python adapter: validates admin tokens and, for the first accepted admin
// link, exposes its write half so the test can push admin `Deliver`s.
// ---------------------------------------------------------------------------

fn spawn_mock_adapter(listener: UnixListener, valid_tokens: HashSet<String>, push: PushLink) {
    tokio::spawn(async move {
        while let Ok((stream, _)) = listener.accept().await {
            tokio::spawn(serve_connection(
                stream,
                valid_tokens.clone(),
                Arc::clone(&push),
            ));
        }
    });
}

async fn serve_connection(stream: UnixStream, valid_tokens: HashSet<String>, push: PushLink) {
    let (mut read, mut write) = stream.into_split();
    // Only `ValidateAdminToken` is expected on an admin link (no session lifecycle);
    // anything else is ignored.
    while let Some(inbound) = read_inbound(&mut read).await {
        if let GatewayInbound::ValidateAdminToken { token } = inbound {
            let accepted = valid_tokens.contains(&token);
            write_outbound(&mut write, &GatewayOutbound::AdminAuthResult { accepted }).await;
            if accepted {
                // Hand this link's write half to the shared push slot (first one
                // wins) so the test can broadcast admin `Deliver`s through it, then
                // keep reading to detect the client close. A `Deliver` fans out to
                // *all* admins regardless of which link carries it.
                let mut slot = push.lock().await;
                if slot.is_none() {
                    *slot = Some(write);
                }
                break;
            }
        }
    }
    // Drain until close so the connection stays alive for pushes.
    while read_inbound(&mut read).await.is_some() {}
}

// ---------------------------------------------------------------------------
// Gateway harness
// ---------------------------------------------------------------------------

struct Harness {
    addr: SocketAddr,
    registry: Arc<ConnectionRegistry>,
    push: PushLink,
    _socket_dir: tempfile::TempDir,
}

impl Harness {
    /// Broadcast one admin `Deliver` down the push link, waiting for the link to be
    /// populated (the first admin authenticated) up to the step budget.
    async fn push_admin(&self, payload: Value) {
        let directive = DeliveryDirective {
            target: DeliveryTarget::Admin,
            exclude: None,
            payload,
            coalesce_key: None,
        };
        let frame = GatewayOutbound::Deliver { directive };
        let deadline = tokio::time::Instant::now() + STEP;
        loop {
            {
                let mut slot = self.push.lock().await;
                if let Some(write) = slot.as_mut() {
                    write_outbound(write, &frame).await;
                    return;
                }
            }
            assert!(
                tokio::time::Instant::now() < deadline,
                "admin push link never became available"
            );
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    }

    async fn await_admin_count(&self, want: usize) {
        let deadline = tokio::time::Instant::now() + STEP;
        while self.registry.admin_count() != want {
            assert!(
                tokio::time::Instant::now() < deadline,
                "admin_count never reached {want} (is {})",
                self.registry.admin_count()
            );
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    }
}

async fn start_gateway(valid_tokens: &[&str], tweak: impl FnOnce(&mut GatewayConfig)) -> Harness {
    let socket_dir = tempfile::tempdir().expect("tempdir");
    let socket_path = socket_dir.path().join("gateway.sock");
    let listener = UnixListener::bind(&socket_path).expect("bind mock adapter");
    let tokens: HashSet<String> = valid_tokens.iter().map(|t| (*t).to_owned()).collect();
    let push: PushLink = Arc::new(Mutex::new(None));
    spawn_mock_adapter(listener, tokens, Arc::clone(&push));

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

    // Pin a small send buffer on the listener; accepted sockets inherit it (Linux),
    // so a stalled console's writer blocks after a small, bounded burst rather than
    // buffering megabytes in the kernel — making the slow-consumer trip deterministic
    // and fast. A well-behaved (reading) console is unaffected: it drains promptly.
    let server_socket = TcpSocket::new_v4().expect("server socket");
    server_socket
        .set_send_buffer_size(8192)
        .expect("shrink send buffer");
    server_socket
        .bind("127.0.0.1:0".parse().expect("addr"))
        .expect("bind :0");
    let tcp = server_socket.listen(1024).expect("listen");
    let addr = tcp.local_addr().expect("local addr");
    tokio::spawn(async move {
        axum::serve(tcp, router).await.expect("gateway serves");
    });

    Harness {
        addr,
        registry,
        push,
        _socket_dir: socket_dir,
    }
}

async fn admin_connect(addr: SocketAddr, token: &str) -> WsClient {
    let (ws, _response) =
        tokio_tungstenite::connect_async(format!("ws://{addr}/admin/ws?token={token}"))
            .await
            .expect("admin websocket upgrade");
    ws
}

/// Connect an admin console whose kernel receive buffer is pinned tiny, so a
/// stalled (non-reading) client's transport buffers fill after a small, bounded
/// burst — making the slow-consumer disconnect deterministic and fast rather than
/// dependent on the host's default/auto-tuned socket buffer sizes.
async fn admin_connect_tiny_rcvbuf(addr: SocketAddr, token: &str) -> WsClient {
    let socket = TcpSocket::new_v4().expect("tcp socket");
    socket
        .set_recv_buffer_size(4096)
        .expect("shrink recv buffer");
    let tcp = socket.connect(addr).await.expect("connect");
    let stream = MaybeTlsStream::Plain(tcp);
    let (ws, _response) =
        tokio_tungstenite::client_async(format!("ws://{addr}/admin/ws?token={token}"), stream)
            .await
            .expect("admin websocket upgrade");
    ws
}

/// Next **text** frame from the client socket, decoded as JSON (skips ping/pong).
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
            _ => {}
        }
    }
}

/// Await the server-initiated close, draining any buffered text frames first.
async fn drain_until_close(ws: &mut WsClient) -> u16 {
    loop {
        let msg = timeout(STEP, ws.next())
            .await
            .expect("close arrives in time")
            .expect("stream still open")
            .expect("frame decodes");
        if let WsMessage::Close(frame) = msg {
            return frame.expect("close carries a code").code.into();
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

/// THE ADMIN HAPPY PATH: a valid token is accepted (after the upgrade), the admin
/// is registered, and an admin `Deliver` pushed by the mock reaches the client.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn admin_valid_token_registers_and_receives_push() {
    let harness = start_gateway(&["good-token"], |_| {}).await;
    let mut admin = admin_connect(harness.addr, "good-token").await;

    // Registration completes once the AdminAuthResult is processed.
    harness.await_admin_count(1).await;

    // The mock broadcasts an admin event; it must reach this console.
    harness
        .push_admin(json!({"type": "admin_event", "kind": "player_joined", "player": "hero"}))
        .await;
    let event = next_text(&mut admin).await;
    assert_eq!(event["type"], json!("admin_event"));
    assert_eq!(event["kind"], json!("player_joined"));
    assert_eq!(event["player"], json!("hero"));
}

/// EXIT-CHECK REQUIREMENT: a bad/expired admin token yields WS close **1008**
/// *after* the upgrade is accepted, preserving the admin UI's 1008-vs-1006
/// distinction (stale-session logout vs. transport drop).
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn admin_bad_token_closes_1008_after_accept() {
    let harness = start_gateway(&["good-token"], |_| {}).await;
    let mut admin = admin_connect(harness.addr, "expired-token").await;

    // The upgrade succeeded (connect_async returned), then Rust closed 1008.
    let code = drain_until_close(&mut admin).await;
    assert_eq!(code, 1008);
    assert_eq!(harness.registry.admin_count(), 0);
}

/// THE SLOW-CLIENT DISCONNECT PROOF (exit-critical, item 3): a stalled admin console
/// (one that stops reading) is bounded and disconnected with **1013** within the
/// overflow threshold, while a co-located admin that keeps reading is completely
/// unaffected — it receives the whole broadcast burst, never blocked, never dropped.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn slow_admin_is_closed_1013_while_fast_sibling_keeps_receiving() {
    // Small threshold so the stalled consumer trips quickly; default queue depth.
    let harness = start_gateway(&["good-token"], |cfg| {
        cfg.backpressure = BackpressureConfig {
            max_consecutive_overflow: 8,
        };
    })
    .await;

    // Fast admin: a task drains it continuously and counts receipts.
    let mut fast = admin_connect(harness.addr, "good-token").await;
    // Slow admin: a pinned-tiny receive buffer + never reading → its transport
    // buffers fill after a small burst, tripping the overflow threshold.
    let mut slow = admin_connect_tiny_rcvbuf(harness.addr, "good-token").await;
    harness.await_admin_count(2).await;

    let (count_tx, count_rx) = tokio::sync::oneshot::channel();
    let fast_reader = tokio::spawn(async move {
        let mut received = 0usize;
        let mut count_tx = Some(count_tx);
        while let Some(Ok(msg)) = fast.next().await {
            if let WsMessage::Text(_) = msg {
                received += 1;
                if received == 200 {
                    if let Some(tx) = count_tx.take() {
                        let _ = tx.send(received);
                    }
                }
            }
        }
        received
    });

    // Broadcast a burst of keyless (never-coalesced) admin events large enough to
    // fill the stalled console's pinned-tiny transport buffers plus its bounded
    // outbound queue and trip the overflow threshold. Each frame carries filler so
    // the buffers fill in a small, bounded number of pushes.
    let filler = "x".repeat(512);
    for seq in 0..3_000u32 {
        harness
            .push_admin(json!({"type": "admin_event", "seq": seq, "filler": filler}))
            .await;
    }

    // The stalled console is deregistered (its close signal fired + teardown ran)
    // while the fast sibling remains — the count drops from 2 to exactly 1.
    harness.await_admin_count(1).await;

    // The fast sibling was unaffected: it drained well past the checkpoint.
    let fast_count = timeout(STEP, count_rx)
        .await
        .expect("fast admin keeps receiving despite the stalled sibling")
        .expect("fast reader reported its count");
    assert!(fast_count >= 200, "fast admin received the broadcast burst");

    // Draining the stalled console now (buffers free up) surfaces the 1013 close.
    let code = drain_until_close(&mut slow).await;
    assert_eq!(
        code, 1013,
        "stalled consumer closed with Try-Again-Later (1013)"
    );

    fast_reader.abort();
}
