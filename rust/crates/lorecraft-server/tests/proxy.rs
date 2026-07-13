//! Hermetic integration tests for the Phase 3b reverse proxy (Option-A front
//! door). A mock upstream `axum` server stands in for Python uvicorn; requests
//! are driven **through** the real gateway router with a redirect-disabled
//! `reqwest` client, asserting transparent passthrough: bodies/status unchanged,
//! `Set-Cookie` survives, a `303` is relayed (not auto-followed), and the local
//! `/healthz` + `/ws` routes keep precedence over the proxy fallback.
//!
//! No real Python and no UDS traffic: the gateway's `ForwardClient` is pointed at
//! a bare Unix listener that merely accepts (the proxy path never touches it).

use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use axum::extract::Request;
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::Router;
use lorecraft_server::lorecraft_events::ConnectionRegistry;
use lorecraft_server::{
    build_router, DisconnectHub, DispatchContext, ForwardClient, GatewayConfig,
};
use tokio::net::{TcpListener, UnixListener};

const LOBBY_HTML: &str = "<html><body>lobby</body></html>";
const SESSION_COOKIE: &str = "lorecraft_session=deadbeef; Path=/; HttpOnly; SameSite=Lax";
const TICKET_JSON: &str = r#"{"ticket":"tkt-12345"}"#;
const REDIRECT_TARGET: &str = "/game";

// ---------------------------------------------------------------------------
// Mock upstream (stands in for Python uvicorn)
// ---------------------------------------------------------------------------

async fn upstream_lobby() -> Response {
    let mut headers = HeaderMap::new();
    headers.insert("set-cookie", SESSION_COOKIE.parse().unwrap());
    headers.insert("content-type", "text/html; charset=utf-8".parse().unwrap());
    (StatusCode::OK, headers, LOBBY_HTML).into_response()
}

async fn upstream_ws_ticket(body: axum::body::Bytes) -> Response {
    // Echo back that we saw the posted body, and hand out a ticket as JSON.
    let mut headers = HeaderMap::new();
    headers.insert("content-type", "application/json".parse().unwrap());
    headers.insert("x-seen-body-len", body.len().to_string().parse().unwrap());
    (StatusCode::OK, headers, TICKET_JSON).into_response()
}

async fn upstream_redirect() -> Response {
    let mut headers = HeaderMap::new();
    headers.insert("location", REDIRECT_TARGET.parse().unwrap());
    (StatusCode::SEE_OTHER, headers).into_response()
}

/// Echo the inbound method + a chosen request header back, to prove the proxy
/// forwards them verbatim.
async fn upstream_echo(req: Request) -> Response {
    let method = req.method().clone();
    let via = req
        .headers()
        .get("x-client-note")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("(none)")
        .to_owned();
    let host = req
        .headers()
        .get("host")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("(none)")
        .to_owned();
    let body = format!("method={method} note={via} host={host}");
    (StatusCode::OK, body).into_response()
}

async fn start_upstream() -> SocketAddr {
    let app = Router::new()
        .route("/lobby", get(upstream_lobby))
        .route("/auth/ws-ticket", post(upstream_ws_ticket))
        .route("/redirect-me", get(upstream_redirect))
        .route("/echo", get(upstream_echo).post(upstream_echo));
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind upstream");
    let addr = listener.local_addr().expect("upstream addr");
    tokio::spawn(async move {
        axum::serve(listener, app).await.expect("upstream serves");
    });
    addr
}

// ---------------------------------------------------------------------------
// Gateway harness (proxy path only — UDS peer just accepts)
// ---------------------------------------------------------------------------

struct Harness {
    addr: SocketAddr,
    _socket_dir: tempfile::TempDir,
}

/// A minimal UDS peer that only accepts connections. The `ForwardClient` the
/// gateway requires connects successfully; the proxy path never sends frames.
fn spawn_bare_uds_peer(listener: UnixListener) {
    tokio::spawn(async move {
        while let Ok((stream, _)) = listener.accept().await {
            // Hold the connection open; never read/write.
            tokio::spawn(async move {
                let _held = stream;
                std::future::pending::<()>().await;
            });
        }
    });
}

async fn start_gateway(backend_url: String) -> Harness {
    let socket_dir = tempfile::tempdir().expect("tempdir");
    let socket_path = socket_dir.path().join("gateway.sock");
    let listener = UnixListener::bind(&socket_path).expect("bind bare uds peer");
    spawn_bare_uds_peer(listener);

    let registry = Arc::new(ConnectionRegistry::new());
    let disconnect = Arc::new(DisconnectHub::new());
    let config = Arc::new(GatewayConfig {
        socket_path: socket_path.clone(),
        backend_url,
        handshake_timeout_ms: 2_000,
        ..GatewayConfig::default()
    });
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
    let router = build_router(config, registry, forward, disconnect);

    let tcp = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind gateway");
    let addr = tcp.local_addr().expect("gateway addr");
    tokio::spawn(async move {
        axum::serve(tcp, router).await.expect("gateway serves");
    });

    Harness {
        addr,
        _socket_dir: socket_dir,
    }
}

/// A `reqwest` client that does **not** follow redirects — mirroring the gateway's
/// own client and letting us assert a 303 is relayed rather than resolved.
fn non_following_client() -> reqwest::Client {
    reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(5))
        .build()
        .expect("test client builds")
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

/// GET is proxied: status, HTML body and the `Set-Cookie` session header all pass
/// through the gateway unchanged.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn get_is_proxied_with_body_and_set_cookie() {
    let upstream = start_upstream().await;
    let harness = start_gateway(format!("http://{upstream}")).await;
    let client = non_following_client();

    let resp = client
        .get(format!("http://{}/lobby", harness.addr))
        .send()
        .await
        .expect("gateway responds");

    assert_eq!(resp.status(), StatusCode::OK);
    let cookie = resp
        .headers()
        .get("set-cookie")
        .expect("Set-Cookie relayed")
        .to_str()
        .unwrap()
        .to_owned();
    assert_eq!(cookie, SESSION_COOKIE, "session cookie must be untouched");
    let content_type = resp
        .headers()
        .get("content-type")
        .expect("content-type relayed")
        .to_str()
        .unwrap()
        .to_owned();
    assert_eq!(content_type, "text/html; charset=utf-8");
    assert_eq!(resp.text().await.unwrap(), LOBBY_HTML);
}

/// POST /auth/ws-ticket round-trips: the request body is forwarded (upstream
/// echoes its length) and the JSON ticket comes back unchanged.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn post_ws_ticket_round_trips_body_and_json() {
    let upstream = start_upstream().await;
    let harness = start_gateway(format!("http://{upstream}")).await;
    let client = non_following_client();

    let payload = r#"{"csrf":"x"}"#;
    let resp = client
        .post(format!("http://{}/auth/ws-ticket", harness.addr))
        .body(payload)
        .send()
        .await
        .expect("gateway responds");

    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        resp.headers()
            .get("x-seen-body-len")
            .and_then(|v| v.to_str().ok()),
        Some(payload.len().to_string().as_str()),
        "upstream saw the forwarded request body"
    );
    assert_eq!(resp.text().await.unwrap(), TICKET_JSON);
}

/// A 303 from the backend is relayed as a 303 with its `Location` intact — the
/// proxy does not follow it, so the browser can.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn redirect_is_relayed_not_followed() {
    let upstream = start_upstream().await;
    let harness = start_gateway(format!("http://{upstream}")).await;
    let client = non_following_client();

    let resp = client
        .get(format!("http://{}/redirect-me", harness.addr))
        .send()
        .await
        .expect("gateway responds");

    assert_eq!(resp.status(), StatusCode::SEE_OTHER);
    assert_eq!(
        resp.headers().get("location").and_then(|v| v.to_str().ok()),
        Some(REDIRECT_TARGET),
        "Location must survive so the browser follows the redirect"
    );
}

/// Method + inbound headers reach the backend, and the client-supplied `Host` is
/// replaced by the upstream authority (the proxy lets the client set it).
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn method_and_headers_are_forwarded_host_is_rewritten() {
    let upstream = start_upstream().await;
    let harness = start_gateway(format!("http://{upstream}")).await;
    let client = non_following_client();

    let resp = client
        .post(format!("http://{}/echo", harness.addr))
        .header("x-client-note", "hello")
        .send()
        .await
        .expect("gateway responds");

    assert_eq!(resp.status(), StatusCode::OK);
    let body = resp.text().await.unwrap();
    assert!(body.contains("method=POST"), "method forwarded: {body}");
    assert!(
        body.contains("note=hello"),
        "custom header forwarded: {body}"
    );
    assert!(
        body.contains(&format!("host={upstream}")),
        "Host is the upstream authority, not the gateway's: {body}"
    );
}

/// `/healthz` is served locally (its JSON `status: ok`), proving the local route
/// wins over the proxy fallback — the mock upstream has no `/healthz` at all.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn healthz_is_served_locally_not_proxied() {
    let upstream = start_upstream().await;
    let harness = start_gateway(format!("http://{upstream}")).await;
    let client = non_following_client();

    let resp = client
        .get(format!("http://{}/healthz", harness.addr))
        .send()
        .await
        .expect("gateway responds");

    assert_eq!(resp.status(), StatusCode::OK);
    // reqwest's `json` feature is intentionally off in this crate; parse the text.
    let body = resp.text().await.expect("healthz body");
    let json: serde_json::Value = serde_json::from_str(&body).expect("healthz returns JSON");
    assert_eq!(json["status"], "ok");
    assert_eq!(json["world_id"], "world-1");
}

/// `/ws` keeps route precedence: a plain (non-upgrade) GET is rejected locally by
/// the WebSocket extractor rather than being proxied to the backend (which has no
/// `/ws`). A proxied miss would surface the upstream's 404; instead we get the
/// upgrade-required rejection, proving the local route matched first.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn ws_route_takes_precedence_over_proxy_fallback() {
    let upstream = start_upstream().await;
    let harness = start_gateway(format!("http://{upstream}")).await;
    let client = non_following_client();

    let resp = client
        .get(format!("http://{}/ws", harness.addr))
        .send()
        .await
        .expect("gateway responds");

    // axum's WebSocketUpgrade rejects a non-upgrade GET with 426/400 — never a
    // proxied upstream 404.
    assert!(
        resp.status() == StatusCode::UPGRADE_REQUIRED || resp.status() == StatusCode::BAD_REQUEST,
        "GET /ws should be handled locally by the WS extractor, got {}",
        resp.status()
    );
    assert_ne!(
        resp.status(),
        StatusCode::NOT_FOUND,
        "a 404 would mean /ws fell through to the proxy"
    );
}
