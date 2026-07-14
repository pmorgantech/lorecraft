//! `lorecraft-gateway` — the Rust gateway binary (Phase 3b).
//!
//! Serves the player `/ws` route (plus `/healthz`) and reverse-proxies every
//! other HTTP request to the Python backend, forwarding commands to the Python
//! adapter's UDS listener. This is the Option-A single front door (Phase 3b): a
//! browser loads the whole app through this port, so the frontend JS builds its
//! WebSocket URL from the Rust origin with no change.
//!
//! Configuration is read from the environment (static operational config,
//! design decision 12):
//!
//! | Variable                        | Default          | Meaning                          |
//! |---------------------------------|------------------|----------------------------------|
//! | `LORECRAFT_GATEWAY_BIND`        | `127.0.0.1:0`    | HTTP/WS bind address (`:0` = OS-assigned port) |
//! | `LORECRAFT_GATEWAY_SOCKET_PATH` | `var/gateway.sock` | Python adapter's UDS socket path |
//! | `LORECRAFT_GATEWAY_WORLD_ID`    | `world-1`        | `world_id` stamped on envelopes  |
//! | `LORECRAFT_GATEWAY_DEADLINE_MS` | `5000`           | `deadline_ms` stamped on envelopes |
//! | `LORECRAFT_GATEWAY_BACKEND`     | `http://127.0.0.1:8000` | Python uvicorn origin the proxy forwards to |
//! | `LORECRAFT_RUST_VERBS`          | `look,north,south,east,west` | Comma-separated verbs Rust executes (Phase 4). **Unset** → the default live-cutover set (`look` + the four cardinal moves). Explicitly **empty** (`LORECRAFT_RUST_VERBS=`) → all commands to Python (rollback) |
//!
//! The Phase-3c slow-client/rate-limit thresholds are also env-overridable. These
//! are primarily for **test determinism** and secondarily for **operator tuning**;
//! when unset the shipped [`GatewayConfig`] defaults apply unchanged. A malformed
//! value is ignored (warned) in favour of the default rather than aborting startup.
//!
//! | Variable                             | Default    | Meaning                                    |
//! |--------------------------------------|------------|--------------------------------------------|
//! | `LORECRAFT_GATEWAY_QUEUE_DEPTH`      | `256`      | Per-connection outbound queue depth        |
//! | `LORECRAFT_GATEWAY_MAX_OVERFLOW`     | `64`       | Consecutive overflows before a slow-consumer close |
//! | `LORECRAFT_GATEWAY_COMMAND_BURST`    | `20`       | Per-player command token-bucket burst      |
//! | `LORECRAFT_GATEWAY_COMMAND_RATE`     | `5.0`      | Per-player sustained command rate (tokens/sec) |
//! | `LORECRAFT_GATEWAY_EXECUTE_MS`       | `5000`     | Backstop timeout for one Rust-executed command's round-trip (Phase 4b) |
//! | `LORECRAFT_GATEWAY_SEND_BUFFER_BYTES`| OS default | `SO_SNDBUF` on the listening socket (inherited by every accepted connection) |
//!
//! `SEND_BUFFER_BYTES` is the load-bearing knob for a *deterministic* slow-client
//! test: with the OS default send buffer (megabytes) a non-reading consumer's kernel
//! buffer absorbs thousands of frames before the writer ever blocks — so the
//! backpressure trip point is dominated by that host-dependent buffer, not by
//! [`QUEUE_DEPTH`]/[`MAX_OVERFLOW`]. Capping `SO_SNDBUF` to a few KB makes the writer
//! block after a handful of frames, so the queue fills and the slow-consumer close
//! fires promptly and host-independently. Unset (the default) it is never touched, so
//! production and every other test keep the OS-tuned buffer.
//!
//! Once serving, it prints exactly one line to stdout in the form
//! `GATEWAY_LISTENING <addr>` (e.g. `GATEWAY_LISTENING 127.0.0.1:43571`) so a
//! test harness binding to `:0` can learn the actual port.

use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use anyhow::Context;
use lorecraft_server::lorecraft_events::ConnectionRegistry;
use lorecraft_server::{
    build_router, DisconnectHub, DispatchContext, ForwardClient, GatewayConfig,
};

/// How many times to retry the initial UDS connect to the Python adapter (it
/// may still be starting when the gateway boots), and the pause between tries.
const CONNECT_ATTEMPTS: u32 = 20;
const CONNECT_RETRY_PAUSE: Duration = Duration::from_millis(250);

/// The default `LORECRAFT_RUST_VERBS` allow-list applied when the variable is
/// **unset** — the Phase 4 live cutover set: `look` (4b) plus the four cardinal
/// movement directions (4c). A real WS client's bare `look`, a bare cardinal
/// (`north`, `n`, …), or the explicit `go <cardinal>` form all route to the Rust
/// pipeline with no configuration. The direction words normalize the alias table,
/// so listing the canonical `north,south,east,west` also covers a typed `n/s/e/w`
/// and the `go n` form (see [`route::parse_allow_list`]/[`route::decide`]).
///
/// Rollback stays a config toggle: setting `LORECRAFT_RUST_VERBS=` (explicitly
/// empty) parses to the empty set, returning every command — `look` and movement
/// included — to the unchanged Phase 3 Python path.
///
/// This default lives at the *binary* boundary, not in
/// [`GatewayConfig::default`](lorecraft_server::GatewayConfig), which stays empty
/// (the safe library default = pure Phase 3): the deployed gateway opts these verbs
/// in, while library/unit consumers of the config default are unaffected.
const DEFAULT_RUST_VERBS: &str = "look,north,south,east,west";

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_owned())
}

/// Parse an optional numeric env override, falling back to `default` when the
/// variable is unset *or* malformed. Unlike the required `BIND`/`DEADLINE_MS`
/// knobs (which abort on a bad value), these Phase-3c operational tunables are
/// best-effort: a malformed value warns and keeps the shipped default rather than
/// downing the gateway, so a stray override never takes production offline.
fn env_parse_or<T: std::str::FromStr>(key: &str, default: T) -> T {
    match std::env::var(key) {
        Err(_) => default,
        Ok(raw) => raw.parse().unwrap_or_else(|_| {
            tracing::warn!(key, value = %raw, "ignoring malformed gateway override; using default");
            default
        }),
    }
}

/// Build the gateway config from the environment (see the module docs table).
fn config_from_env() -> anyhow::Result<GatewayConfig> {
    let bind_raw = env_or("LORECRAFT_GATEWAY_BIND", "127.0.0.1:0");
    let bind_address: SocketAddr = bind_raw
        .parse()
        .with_context(|| format!("LORECRAFT_GATEWAY_BIND is not a socket address: {bind_raw}"))?;
    let deadline_raw = env_or("LORECRAFT_GATEWAY_DEADLINE_MS", "5000");
    let default_deadline_ms: u64 = deadline_raw.parse().with_context(|| {
        format!("LORECRAFT_GATEWAY_DEADLINE_MS is not an integer: {deadline_raw}")
    })?;
    let mut config = GatewayConfig {
        bind_address,
        socket_path: PathBuf::from(env_or("LORECRAFT_GATEWAY_SOCKET_PATH", "var/gateway.sock")),
        world_id: env_or("LORECRAFT_GATEWAY_WORLD_ID", "world-1"),
        backend_url: env_or("LORECRAFT_GATEWAY_BACKEND", "http://127.0.0.1:8000"),
        default_deadline_ms,
        ..GatewayConfig::default()
    };
    // Phase-3c slow-client/rate-limit overrides (see the module docs). Each falls
    // back to the shipped default when unset or malformed, so production and the
    // non-overriding tests are unchanged.
    config.outbound_queue_depth =
        env_parse_or("LORECRAFT_GATEWAY_QUEUE_DEPTH", config.outbound_queue_depth);
    config.backpressure.max_consecutive_overflow = env_parse_or(
        "LORECRAFT_GATEWAY_MAX_OVERFLOW",
        config.backpressure.max_consecutive_overflow,
    );
    config.rate_limit.burst =
        env_parse_or("LORECRAFT_GATEWAY_COMMAND_BURST", config.rate_limit.burst);
    config.rate_limit.per_second = env_parse_or(
        "LORECRAFT_GATEWAY_COMMAND_RATE",
        config.rate_limit.per_second,
    );
    // Phase 4b execution round-trip backstop: bounds one Rust-executed command's
    // whole BuildSnapshot/ApplyOutcome conversation so a mute Python peer can never
    // wedge the receive loop. Falls back to the shipped default when unset/malformed.
    config.execute_timeout_ms =
        env_parse_or("LORECRAFT_GATEWAY_EXECUTE_MS", config.execute_timeout_ms);
    // Phase 4 verb allow-list (decision 3). Live cutover (4b): the variable
    // **unset** defaults to `DEFAULT_RUST_VERBS` (`look`), so a real WS client's
    // bare `look` is Rust-executed with no configuration. Setting it explicitly
    // **empty** (`LORECRAFT_RUST_VERBS=`) parses to the empty set → every command
    // routes to Python (pure Phase 3 rollback). `std::env::var` distinguishes the
    // two: unset yields `Err` (→ default), explicit-empty yields `Ok("")` (→ empty).
    config.rust_verbs = lorecraft_server::route::parse_allow_list(&env_or(
        "LORECRAFT_RUST_VERBS",
        DEFAULT_RUST_VERBS,
    ));
    Ok(config)
}

/// Bind the HTTP/WS listener, optionally capping `SO_SNDBUF` on the listening
/// socket (Linux inherits it onto every accepted connection).
///
/// When `send_buffer_bytes` is `None` this is exactly `TcpListener::bind` — the OS
/// keeps its autotuned (multi-megabyte) send buffer, so production is unchanged.
/// When `Some`, the buffer is pinned small: a non-reading consumer's kernel buffer
/// then fills after only a handful of frames, so the writer blocks and the
/// slow-consumer backpressure trip fires promptly and host-independently (the
/// enabler for the deterministic slow-client simulation). `SO_REUSEADDR` is set to
/// match `TcpListener::bind`'s default on Unix.
async fn bind_listener(
    addr: SocketAddr,
    send_buffer_bytes: Option<u32>,
) -> anyhow::Result<tokio::net::TcpListener> {
    let Some(bytes) = send_buffer_bytes else {
        return tokio::net::TcpListener::bind(addr)
            .await
            .with_context(|| format!("could not bind {addr}"));
    };
    let socket = match addr {
        SocketAddr::V4(_) => tokio::net::TcpSocket::new_v4(),
        SocketAddr::V6(_) => tokio::net::TcpSocket::new_v6(),
    }
    .context("could not create listening socket")?;
    socket
        .set_reuseaddr(true)
        .context("could not set SO_REUSEADDR")?;
    socket
        .set_send_buffer_size(bytes)
        .with_context(|| format!("could not set SO_SNDBUF={bytes}"))?;
    socket
        .bind(addr)
        .with_context(|| format!("could not bind {addr}"))?;
    socket
        .listen(1024)
        .with_context(|| format!("could not listen on {addr}"))
}

/// Connect the shared (health-check/admin) forward link, retrying briefly so
/// gateway-before-adapter startup ordering isn't fatal.
async fn connect_with_retry(
    socket_path: &Path,
    ctx: DispatchContext,
) -> anyhow::Result<ForwardClient> {
    let mut last_err: Option<lorecraft_server::ForwardError> = None;
    for attempt in 1..=CONNECT_ATTEMPTS {
        match ForwardClient::connect(socket_path, ctx.clone()).await {
            Ok(client) => return Ok(client),
            Err(err) => {
                tracing::info!(
                    attempt,
                    error = %err,
                    socket = %socket_path.display(),
                    "python adapter not reachable yet; retrying"
                );
                last_err = Some(err);
                tokio::time::sleep(CONNECT_RETRY_PAUSE).await;
            }
        }
    }
    Err(anyhow::anyhow!(
        "could not reach the python adapter at {} after {CONNECT_ATTEMPTS} attempts: {}",
        socket_path.display(),
        // Loop above always sets last_err before falling through.
        last_err.map_or_else(|| "unknown".to_owned(), |e| e.to_string()),
    ))
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr) // keep stdout clean for GATEWAY_LISTENING
        .init();

    let config = Arc::new(config_from_env()?);
    // Optional `SO_SNDBUF` cap (see the module docs) — read here, not in
    // `GatewayConfig`, because it only shapes how `main` builds the listener socket
    // and never flows into the request handlers. Unset → OS default (untouched).
    let send_buffer_bytes: Option<u32> = match std::env::var("LORECRAFT_GATEWAY_SEND_BUFFER_BYTES")
    {
        Err(_) => None,
        Ok(raw) => match raw.parse::<u32>() {
            Ok(bytes) => Some(bytes),
            Err(_) => {
                tracing::warn!(
                    value = %raw,
                    "ignoring malformed LORECRAFT_GATEWAY_SEND_BUFFER_BYTES; using OS default"
                );
                None
            }
        },
    };
    // Log the effective operational knobs once at startup so an operator (or a test)
    // can confirm which backpressure / rate-limit thresholds are actually in force.
    tracing::info!(
        outbound_queue_depth = config.outbound_queue_depth,
        max_consecutive_overflow = config.backpressure.max_consecutive_overflow,
        command_burst = config.rate_limit.burst,
        command_rate_per_sec = config.rate_limit.per_second,
        send_buffer_bytes = ?send_buffer_bytes,
        "gateway backpressure/rate-limit config"
    );
    let registry = Arc::new(ConnectionRegistry::new());
    let disconnect = Arc::new(DisconnectHub::new());
    let ctx = DispatchContext::new(
        Arc::clone(&registry),
        Arc::clone(&disconnect),
        config.backpressure,
    );
    let forward = Arc::new(connect_with_retry(&config.socket_path, ctx).await?);

    let listener = bind_listener(config.bind_address, send_buffer_bytes).await?;
    let addr = listener
        .local_addr()
        .context("bound listener has no address")?;
    // The harness contract: one parseable stdout line once serving.
    println!("GATEWAY_LISTENING {addr}");

    let router = build_router(config, registry, forward, disconnect);
    axum::serve(listener, router)
        .await
        .context("gateway server exited with an error")?;
    Ok(())
}
