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
use lorecraft_server::{build_router, ForwardClient, GatewayConfig};

/// How many times to retry the initial UDS connect to the Python adapter (it
/// may still be starting when the gateway boots), and the pause between tries.
const CONNECT_ATTEMPTS: u32 = 20;
const CONNECT_RETRY_PAUSE: Duration = Duration::from_millis(250);

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_owned())
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
    Ok(GatewayConfig {
        bind_address,
        socket_path: PathBuf::from(env_or("LORECRAFT_GATEWAY_SOCKET_PATH", "var/gateway.sock")),
        world_id: env_or("LORECRAFT_GATEWAY_WORLD_ID", "world-1"),
        backend_url: env_or("LORECRAFT_GATEWAY_BACKEND", "http://127.0.0.1:8000"),
        default_deadline_ms,
        ..GatewayConfig::default()
    })
}

/// Connect the shared (health-check/admin) forward link, retrying briefly so
/// gateway-before-adapter startup ordering isn't fatal.
async fn connect_with_retry(
    socket_path: &Path,
    registry: Arc<ConnectionRegistry>,
) -> anyhow::Result<ForwardClient> {
    let mut last_err: Option<lorecraft_server::ForwardError> = None;
    for attempt in 1..=CONNECT_ATTEMPTS {
        match ForwardClient::connect(socket_path, Arc::clone(&registry)).await {
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
    let registry = Arc::new(ConnectionRegistry::new());
    let forward = Arc::new(connect_with_retry(&config.socket_path, Arc::clone(&registry)).await?);

    let listener = tokio::net::TcpListener::bind(config.bind_address)
        .await
        .with_context(|| format!("could not bind {}", config.bind_address))?;
    let addr = listener
        .local_addr()
        .context("bound listener has no address")?;
    // The harness contract: one parseable stdout line once serving.
    println!("GATEWAY_LISTENING {addr}");

    let router = build_router(config, registry, forward);
    axum::serve(listener, router)
        .await
        .context("gateway server exited with an error")?;
    Ok(())
}
