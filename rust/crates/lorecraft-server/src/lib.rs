//! lorecraft-server — the Phase 3 Axum HTTP/WS ingress + Rust-side UDS forwarding
//! client (design decision 9).
//!
//! The gateway owns client sockets and forwards commands to the existing Python
//! command processor over a Unix-domain socket carrying length-prefixed JSON
//! frames (decision 2), relaying Python's fan-out directives into the Rust-owned
//! [`lorecraft_events::ConnectionRegistry`]. This crate composes:
//!
//! - [`forward`] — the framed UDS client to the Python adapter: a background
//!   read loop demultiplexes correlated `CommandReply`s, sequential control
//!   replies (`AuthResult`/`ConnectAck`), and un-correlated `Deliver` pushes.
//!   One `ForwardClient` is opened **per player connection** (see its module
//!   docs for the resolved design decision).
//! - [`gateway`] — the Axum router/app + static config. The `lorecraft-gateway`
//!   binary (`src/bin/gateway.rs`) serves it.
//! - `proxy` (private) — the transparent HTTP reverse proxy (Phase 3b, Option A):
//!   the router's `.fallback(...)` forwards every non-`/ws`/`/healthz` request to
//!   the Python backend verbatim, making the gateway the single front door.
//! - [`ws_player`] — the **live** player `/ws` cutover (Phase 3b): ticket auth
//!   handoff, connect handshake, per-connection writer task, receive loop, plus
//!   (Phase 3c) a per-player command rate limit.
//! - [`ws_admin`] / [`auth::validate_admin_token`] — the **live** admin `/admin/ws`
//!   cutover (Phase 3c): accept-before-validate `?token=` handoff (1008-vs-1006),
//!   push-only writer.
//! - [`disconnect`] — the slow-client close-signal hub + shared [`DispatchContext`]
//!   (Phase 3c, item 3): a dispatch-detected outbound overflow closes the stalled
//!   connection's socket with WS 1013 without blocking a co-located sibling.
//! - `writer` (private) — the shared per-connection outbound writer: coalescing
//!   keep-latest drain + the 1013 slow-client close (Phase 3c, items 3–4).

#![warn(missing_docs)]

pub mod auth;
pub mod disconnect;
pub mod forward;
pub mod gateway;
mod proxy;
mod writer;
pub mod ws_admin;
pub mod ws_player;

pub use disconnect::{DisconnectHub, DispatchContext};
pub use forward::{AuthDecision, ForwardClient, ForwardError, SessionAck};
pub use gateway::{build_router, GatewayConfig, GatewayState};
pub use lorecraft_events;
pub use lorecraft_protocol;
