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
//! The slow-client *mechanism* (sustained-overflow disconnect signalling, the
//! keep-latest coalescing queue, and the command rate-limit token bucket) lives in
//! [`backpressure`] (Phase 3c). It is Tier 1: policy — *which* frames coalesce, the
//! disconnect threshold, the rate budget — is supplied as data/config by the caller
//! (see the module docs). Admin consoles are tracked by the sibling [`admins`]
//! registry and share the same fan-out + backpressure treatment as players.

#![warn(missing_docs)]

pub mod admins;
pub mod backpressure;
pub mod connections;
pub mod dispatch;

pub use admins::{AdminId, AdminRegistry};
pub use backpressure::{
    BackpressureConfig, BackpressureDisconnect, CoalescingQueue, EnqueueOutcome, OverflowTracker,
    RateLimitConfig, TokenBucket, DEFAULT_COALESCE_QUEUE_CAPACITY, DEFAULT_COMMAND_BURST,
    DEFAULT_COMMAND_RATE_PER_SEC, DEFAULT_MAX_CONSECUTIVE_OVERFLOW,
};
pub use connections::{ConnectionRegistry, OutboundFrame, OutboundPayload, OutboundSender};
pub use dispatch::{
    dispatch, dispatch_with_config, outbound_channel, DeliveryFailure, DisconnectDirective,
    DispatchReport, Recipient, SendError, DEFAULT_OUTBOUND_QUEUE_DEPTH,
};
pub use lorecraft_protocol;
