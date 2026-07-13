//! lorecraft-events — the Rust-owned connection-map + fan-out mechanism.
//!
//! This crate is the headless, unit-testable core of the Phase 3 gateway
//! (design decision 9). It owns the authoritative connection registry and the
//! bounded, non-blocking fan-out dispatch, with no dependency on a live socket or
//! web host:
//!
//! - [`ConnectionRegistry`] ([`connections`]) — the three connection maps
//!   (`player -> outbound handle`, `player -> room`, `room -> players`) with
//!   sorted, deterministic reads mirroring Python's `ConnectionManager`.
//! - [`dispatch`] — resolves a [`lorecraft_protocol::gateway::DeliveryDirective`]
//!   against the registry and relays its opaque payload into each recipient's
//!   bounded outbound queue via a non-blocking `try_send`, so one slow client
//!   never head-of-line-blocks a broadcast.
//!
//! The slow-client *policy* (sustained-overflow disconnect, frame coalescing)
//! lives in a future `backpressure` module (task 3c); this crate provides only
//! the bounded-queue + `try_send` mechanism it will extend.

#![warn(missing_docs)]

pub mod connections;
pub mod dispatch;

pub use connections::{ConnectionRegistry, OutboundPayload, OutboundSender};
pub use dispatch::{
    dispatch, outbound_channel, DeliveryFailure, DispatchReport, SendError,
    DEFAULT_OUTBOUND_QUEUE_DEPTH,
};
pub use lorecraft_protocol;
