//! lorecraft-server — the Phase 3 Axum HTTP/WS ingress + Rust-side UDS forwarding
//! client (design decision 9).
//!
//! The gateway owns client sockets and forwards commands to the existing Python
//! command processor over a Unix-domain socket carrying length-prefixed JSON
//! frames (decision 2), relaying Python's fan-out directives into the Rust-owned
//! [`lorecraft_events::ConnectionRegistry`]. This crate composes:
//!
//! - [`forward`] — the framed UDS client to the Python adapter (the substantive
//!   3a deliverable): a background read loop demultiplexes correlated
//!   `CommandReply`s from un-correlated `Deliver` pushes.
//! - [`gateway`] — the Axum router/app skeleton + static config.
//! - [`ws_player`] / [`ws_admin`] / [`auth`] — honestly-scoped stubs establishing
//!   the file layout the 3b (player socket + ticket auth) and 3c (admin socket +
//!   token auth) cutovers fill in additively.
//!
//! 3a scope is explicitly "routes not yet serving real clients" — the live
//! `/ws`/`/admin/ws` cutover is 3b/3c.

#![warn(missing_docs)]

pub mod auth;
pub mod forward;
pub mod gateway;
pub mod ws_admin;
pub mod ws_player;

pub use forward::{ForwardClient, ForwardError};
pub use gateway::{build_router, GatewayConfig, GatewayState};
pub use lorecraft_events;
pub use lorecraft_protocol;
