//! Slow-client backpressure + outbound-queue coalescing + command rate limiting —
//! the **Tier 1 mechanism** half of Phase 3c design decision 10.
//!
//! Player connections have *no* current outbound limit (see the migration plan's
//! Phase 3 kickoff), so this is **new protective behavior**, not a port of an
//! existing rule: the goal is to *bound* a client that has stopped reading (a full
//! outbound queue that never drains) so it cannot grow memory unboundedly or, in
//! the sequential-await Python model, stall its co-recipients. It must do so
//! **without** regressing well-behaved clients and **without** blocking a
//! co-located sibling — preserving the non-blocking `try_send` property `dispatch`
//! already guarantees (design decision 9).
//!
//! This module is deliberately **policy-free** (decision 11): it never inspects a
//! frame's opaque payload nor decides *which* frames coalesce, *what* the disconnect
//! threshold should mean for a given feature, or *how many* commands a player may
//! send. Those are Tier 2 policy, supplied as data/config:
//!
//! - the disconnect threshold arrives as [`BackpressureConfig`] (a static
//!   *operational* tunable this phase — decision 12 — a named constant, not a magic
//!   number, and not the live-tunable `WorldClock` pattern which is for
//!   *game-balance* dials);
//! - which frames coalesce arrives as the wire-level
//!   [`DeliveryDirective::coalesce_key`](lorecraft_protocol::gateway::DeliveryDirective::coalesce_key),
//!   stamped by the Python policy owner — the [`CoalescingQueue`] here only honors
//!   the key, it never derives one from a payload;
//! - the rate-limit budget arrives as [`RateLimitConfig`].
//!
//! Nothing here reaches for a wall clock in its *detection* path: sustained
//! overflow is counted in consecutive `try_send` failures ([`OverflowTracker`]),
//! keeping the mechanism deterministic and headless-testable with no injected
//! clock. The one inherently time-based primitive, [`TokenBucket`], takes the
//! current instant as an explicit argument so tests drive time without sleeping and
//! no `Instant::now()` hides in the mechanism.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::{Duration, Instant};

use crate::connections::OutboundPayload;

/// Consecutive outbound-overflow (`try_send` full) failures a single connection may
/// accumulate before it is signalled for a [`BackpressureDisconnect::SlowConsumer`]
/// teardown.
///
/// A static operational tunable (decision 12): a named constant, not a magic
/// number, and *not* the live-tunable `WorldClock` pattern (that is reserved for
/// game-balance dials an admin retunes). With the default queue depth
/// ([`crate::DEFAULT_OUTBOUND_QUEUE_DEPTH`] = 256) a client must fail to drain its
/// already-full queue across this many *successive* broadcasts — a genuinely
/// stalled consumer, not a transient burst — before it is dropped.
pub const DEFAULT_MAX_CONSECUTIVE_OVERFLOW: u32 = 64;

/// Default capacity of a per-connection [`CoalescingQueue`]. Matches
/// [`crate::DEFAULT_OUTBOUND_QUEUE_DEPTH`] so a connection's coalescing buffer and
/// its bounded transport queue share one depth budget.
pub const DEFAULT_COALESCE_QUEUE_CAPACITY: usize = crate::DEFAULT_OUTBOUND_QUEUE_DEPTH;

/// Default per-player command burst allowance (token-bucket capacity). Generous by
/// design (decision 10): a well-behaved interactive client never approaches it, so
/// only an abusive flood is throttled.
pub const DEFAULT_COMMAND_BURST: u32 = 20;

/// Default sustained per-player command rate (tokens refilled per second). Also
/// generous — several commands/second is far above human interactive cadence.
pub const DEFAULT_COMMAND_RATE_PER_SEC: f64 = 5.0;

/// Static operational configuration for the slow-client disconnect mechanism.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BackpressureConfig {
    /// Consecutive overflow failures that trip a slow-consumer disconnect.
    pub max_consecutive_overflow: u32,
}

impl Default for BackpressureConfig {
    fn default() -> Self {
        Self {
            max_consecutive_overflow: DEFAULT_MAX_CONSECUTIVE_OVERFLOW,
        }
    }
}

/// A gateway-initiated disconnect signal. This is a **Rust-local** teardown
/// decision (distinct from the Python-facing
/// [`lorecraft_protocol::gateway::DisconnectReason`], which describes *how a client
/// went away*): the gateway itself decides to drop a misbehaving connection. The
/// server task maps it to a concrete WebSocket close code and performs the close;
/// this crate only *names the reason*, keeping it socket-agnostic and testable.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum BackpressureDisconnect {
    /// The connection's outbound queue stayed full across
    /// [`BackpressureConfig::max_consecutive_overflow`] successive sends — the
    /// client stopped reading. The server closes it (recommended
    /// [`Self::ws_close_code`] `1013`, "Try Again Later").
    SlowConsumer,
}

impl BackpressureDisconnect {
    /// The WebSocket close code the server should use for this reason. `1013`
    /// ("Try Again Later") signals transient overload for a slow consumer; the
    /// actual close is the server task's job (this crate touches no socket).
    pub const fn ws_close_code(self) -> u16 {
        match self {
            Self::SlowConsumer => 1013,
        }
    }

    /// A stable, log-friendly label for the reason.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::SlowConsumer => "slow_consumer",
        }
    }
}

/// Per-connection sustained-overflow detector. Interior-mutable (a single relaxed
/// atomic) so `dispatch` can update it while holding only a read lock on the shared
/// registry and without a per-send heap allocation.
///
/// The streak counts **consecutive** `try_send`-full failures: any successful send
/// resets it to zero, so a client that briefly overflows during a burst but keeps
/// draining never trips the threshold — only a genuinely stalled consumer does.
#[derive(Debug, Default)]
pub struct OverflowTracker {
    consecutive: AtomicU32,
}

impl OverflowTracker {
    /// Create a tracker with a clean (zero) streak.
    pub fn new() -> Self {
        Self::default()
    }

    /// Record a successful enqueue: the consumer is draining, so reset the streak.
    pub fn record_success(&self) {
        self.consecutive.store(0, Ordering::Relaxed);
    }

    /// Record an outbound overflow (a `try_send`-full). Returns `true` **exactly
    /// once** — on the send that makes the streak reach
    /// [`BackpressureConfig::max_consecutive_overflow`] — so the caller signals a
    /// disconnect a single time and then tears the connection down. Later overflow
    /// records (streak already past the threshold) return `false`.
    pub fn record_overflow(&self, config: &BackpressureConfig) -> bool {
        let streak = self
            .consecutive
            .fetch_add(1, Ordering::Relaxed)
            .saturating_add(1);
        streak == config.max_consecutive_overflow
    }

    /// The current consecutive-overflow streak (for tests / diagnostics).
    pub fn consecutive(&self) -> u32 {
        self.consecutive.load(Ordering::Relaxed)
    }
}

/// The outcome of enqueuing one frame into a [`CoalescingQueue`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EnqueueOutcome {
    /// A new entry was appended (queue length grew by one).
    Queued,
    /// The frame carried a coalesce key matching an already-queued entry, whose
    /// payload was replaced in place (keep-latest) — the queue did **not** grow.
    Coalesced,
    /// The queue was at capacity and the frame carried no coalescible slot, so it
    /// was rejected. The caller treats this as an overflow (feed it to an
    /// [`OverflowTracker`]).
    Full,
}

/// One buffered outbound frame plus its optional coalesce key.
#[derive(Debug, Clone)]
struct QueuedFrame {
    payload: OutboundPayload,
    coalesce_key: Option<String>,
}

/// A bounded, keep-latest outbound queue — the Tier 1 *mechanism* for design
/// decision 10's coalescing. It sits in front of a connection's socket writer
/// drain: the fan-out producer enqueues frames, the writer task dequeues them in
/// FIFO order.
///
/// The mechanism is payload-blind. Coalescing is driven **only** by the wire-level
/// [`DeliveryDirective::coalesce_key`](lorecraft_protocol::gateway::DeliveryDirective::coalesce_key)
/// the Python policy owner stamps: enqueuing a frame whose key equals an
/// already-queued frame's key replaces that entry's payload *in place* (preserving
/// its position in the stream) rather than growing the queue — so a stalled
/// consumer that later drains sees only the newest state per panel. Frames with no
/// key (e.g. `feed_append`) never coalesce and always occupy their own slot, so no
/// event is silently dropped.
///
/// It is intentionally a plain data structure with no async and no clock, so it is
/// exhaustively unit-testable; the server (a later task) owns wrapping it with the
/// [`tokio::sync::Notify`](https://docs.rs/tokio) wakeup that drives its writer
/// task. Capacity is checked against a linear scan for the matching key, which is
/// cheap for the bounded depths used here and avoids the index-invalidation bugs a
/// side map would introduce against a shifting [`VecDeque`].
#[derive(Debug)]
pub struct CoalescingQueue {
    entries: VecDeque<QueuedFrame>,
    capacity: usize,
}

impl CoalescingQueue {
    /// Create an empty queue bounded to `capacity` entries. A `capacity` of zero is
    /// clamped to one so the queue can always hold at least the latest frame.
    pub fn new(capacity: usize) -> Self {
        Self {
            entries: VecDeque::new(),
            capacity: capacity.max(1),
        }
    }

    /// Create a queue at [`DEFAULT_COALESCE_QUEUE_CAPACITY`].
    pub fn with_default_capacity() -> Self {
        Self::new(DEFAULT_COALESCE_QUEUE_CAPACITY)
    }

    /// The queue's bounded capacity.
    pub fn capacity(&self) -> usize {
        self.capacity
    }

    /// Number of buffered frames.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// Whether the queue holds no frames.
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// Enqueue one frame. If `coalesce_key` is `Some` and matches an already-queued
    /// frame, that frame's payload is replaced in place (keep-latest) and the queue
    /// does not grow; otherwise the frame is appended if there is room, or rejected
    /// as [`EnqueueOutcome::Full`] at capacity. Keyless frames never coalesce.
    pub fn enqueue(
        &mut self,
        payload: OutboundPayload,
        coalesce_key: Option<String>,
    ) -> EnqueueOutcome {
        if let Some(key) = coalesce_key.as_deref() {
            if let Some(slot) = self
                .entries
                .iter_mut()
                .find(|frame| frame.coalesce_key.as_deref() == Some(key))
            {
                slot.payload = payload;
                return EnqueueOutcome::Coalesced;
            }
        }
        if self.entries.len() >= self.capacity {
            return EnqueueOutcome::Full;
        }
        self.entries.push_back(QueuedFrame {
            payload,
            coalesce_key,
        });
        EnqueueOutcome::Queued
    }

    /// Remove and return the oldest buffered payload (FIFO), or `None` if empty.
    pub fn dequeue(&mut self) -> Option<OutboundPayload> {
        self.entries.pop_front().map(|frame| frame.payload)
    }
}

/// A monotonic token bucket — the Tier 1 *mechanism* for design decision 10's new,
/// generous-by-default per-player command rate limit. Policy (the burst/rate
/// values) is supplied via [`RateLimitConfig`]; the server applies it to command
/// intake in a later task.
///
/// Time is an **explicit argument** to every operation ([`Self::try_acquire`] takes
/// the current [`Instant`]): the mechanism holds no clock, so it is deterministic
/// and tests drive refill by passing synthetic instants — no sleeping, and no
/// `Instant::now()` buried in mechanics. The server passes a real `Instant::now()`.
#[derive(Debug, Clone, Copy)]
pub struct RateLimitConfig {
    /// Maximum burst — the bucket's token capacity.
    pub burst: u32,
    /// Sustained refill rate in tokens per second.
    pub per_second: f64,
}

impl Default for RateLimitConfig {
    fn default() -> Self {
        Self {
            burst: DEFAULT_COMMAND_BURST,
            per_second: DEFAULT_COMMAND_RATE_PER_SEC,
        }
    }
}

/// A per-connection token bucket. Construct with [`Self::new`], then gate each
/// command with [`Self::try_acquire`].
#[derive(Debug, Clone)]
pub struct TokenBucket {
    capacity: f64,
    per_second: f64,
    tokens: f64,
    last_refill: Instant,
}

impl TokenBucket {
    /// Create a full bucket as of `now` from a [`RateLimitConfig`].
    pub fn new(config: RateLimitConfig, now: Instant) -> Self {
        let capacity = f64::from(config.burst.max(1));
        Self {
            capacity,
            per_second: config.per_second.max(0.0),
            tokens: capacity,
            last_refill: now,
        }
    }

    /// Refill accrued tokens up to `now`, then attempt to spend one. Returns `true`
    /// if a token was available (the command is admitted) or `false` if the bucket
    /// is empty (the command is throttled). Time only moves forward: a `now` earlier
    /// than the last refill accrues nothing.
    pub fn try_acquire(&mut self, now: Instant) -> bool {
        self.refill(now);
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            true
        } else {
            false
        }
    }

    /// Currently available whole tokens (for tests / diagnostics).
    pub fn available(&self) -> u32 {
        self.tokens.floor().max(0.0) as u32
    }

    fn refill(&mut self, now: Instant) {
        let elapsed = now.saturating_duration_since(self.last_refill);
        if elapsed == Duration::ZERO {
            return;
        }
        self.last_refill = now;
        self.tokens = (self.tokens + elapsed.as_secs_f64() * self.per_second).min(self.capacity);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // --- OverflowTracker ---------------------------------------------------

    #[test]
    fn overflow_tracker_trips_exactly_at_threshold_then_stays_quiet() {
        let cfg = BackpressureConfig {
            max_consecutive_overflow: 3,
        };
        let tracker = OverflowTracker::new();
        assert!(!tracker.record_overflow(&cfg), "streak 1 < 3");
        assert!(!tracker.record_overflow(&cfg), "streak 2 < 3");
        assert!(tracker.record_overflow(&cfg), "streak 3 == 3 trips once");
        assert!(
            !tracker.record_overflow(&cfg),
            "streak 4 > 3 must not re-signal"
        );
        assert_eq!(tracker.consecutive(), 4);
    }

    #[test]
    fn overflow_tracker_success_resets_the_streak() {
        let cfg = BackpressureConfig {
            max_consecutive_overflow: 2,
        };
        let tracker = OverflowTracker::new();
        assert!(!tracker.record_overflow(&cfg));
        tracker.record_success();
        assert_eq!(tracker.consecutive(), 0);
        // A drained client never trips even after many isolated overflows.
        assert!(!tracker.record_overflow(&cfg));
    }

    // --- CoalescingQueue ---------------------------------------------------

    #[test]
    fn same_key_frames_coalesce_to_latest_without_growing() {
        let mut q = CoalescingQueue::new(16);
        for i in 0..5 {
            let outcome = q.enqueue(json!({"panel": "map", "v": i}), Some("panel:map".into()));
            if i == 0 {
                assert_eq!(outcome, EnqueueOutcome::Queued);
            } else {
                assert_eq!(outcome, EnqueueOutcome::Coalesced);
            }
        }
        assert_eq!(q.len(), 1, "five same-key frames collapse to one slot");
        assert_eq!(
            q.dequeue(),
            Some(json!({"panel": "map", "v": 4})),
            "keep-latest"
        );
        assert!(q.dequeue().is_none());
    }

    #[test]
    fn keyless_frames_all_survive_in_fifo_order() {
        let mut q = CoalescingQueue::new(16);
        for i in 0..5 {
            assert_eq!(
                q.enqueue(json!({"feed": i}), None),
                EnqueueOutcome::Queued,
                "no key never coalesces"
            );
        }
        assert_eq!(q.len(), 5);
        for i in 0..5 {
            assert_eq!(q.dequeue(), Some(json!({"feed": i})));
        }
        assert!(q.dequeue().is_none());
    }

    #[test]
    fn coalescing_preserves_stream_position_of_the_slot() {
        // A coalesced frame keeps its original position relative to keyless frames.
        let mut q = CoalescingQueue::new(16);
        assert_eq!(
            q.enqueue(json!({"panel": 0}), Some("p".into())),
            EnqueueOutcome::Queued
        );
        assert_eq!(
            q.enqueue(json!({"feed": "a"}), None),
            EnqueueOutcome::Queued
        );
        assert_eq!(
            q.enqueue(json!({"panel": 9}), Some("p".into())),
            EnqueueOutcome::Coalesced
        );
        // Panel slot (position 0) now holds the latest value; feed is untouched.
        assert_eq!(q.dequeue(), Some(json!({"panel": 9})));
        assert_eq!(q.dequeue(), Some(json!({"feed": "a"})));
    }

    #[test]
    fn full_keyless_queue_reports_overflow() {
        let mut q = CoalescingQueue::new(2);
        assert_eq!(q.enqueue(json!(1), None), EnqueueOutcome::Queued);
        assert_eq!(q.enqueue(json!(2), None), EnqueueOutcome::Queued);
        assert_eq!(q.enqueue(json!(3), None), EnqueueOutcome::Full);
        // A keyed frame matching a queued one still coalesces even when full...
        assert_eq!(q.enqueue(json!(2), Some("k".into())), EnqueueOutcome::Full);
    }

    #[test]
    fn capacity_is_clamped_to_at_least_one() {
        let mut q = CoalescingQueue::new(0);
        assert_eq!(q.capacity(), 1);
        assert_eq!(q.enqueue(json!("only"), None), EnqueueOutcome::Queued);
        assert_eq!(q.enqueue(json!("nope"), None), EnqueueOutcome::Full);
    }

    // --- TokenBucket -------------------------------------------------------

    #[test]
    fn token_bucket_allows_burst_then_throttles() {
        let now = Instant::now();
        let mut bucket = TokenBucket::new(
            RateLimitConfig {
                burst: 5,
                per_second: 1.0,
            },
            now,
        );
        for _ in 0..5 {
            assert!(bucket.try_acquire(now), "burst is admitted");
        }
        assert!(
            !bucket.try_acquire(now),
            "6th within the same instant is throttled"
        );
    }

    #[test]
    fn token_bucket_refills_over_time_up_to_capacity() {
        let t0 = Instant::now();
        let mut bucket = TokenBucket::new(
            RateLimitConfig {
                burst: 5,
                per_second: 2.0,
            },
            t0,
        );
        for _ in 0..5 {
            assert!(bucket.try_acquire(t0));
        }
        assert!(!bucket.try_acquire(t0));
        // After 1 second at 2 tokens/sec, exactly two more are admitted.
        let t1 = t0 + Duration::from_secs(1);
        assert!(bucket.try_acquire(t1));
        assert!(bucket.try_acquire(t1));
        assert!(!bucket.try_acquire(t1), "only two accrued in one second");
        // Refill never exceeds capacity even after a long idle period.
        let t2 = t1 + Duration::from_secs(60);
        assert_eq!(
            {
                bucket.try_acquire(t2);
                bucket.available()
            },
            4,
            "capped at burst(5) then one spent leaves 4"
        );
    }

    #[test]
    fn token_bucket_ignores_backward_time() {
        let t0 = Instant::now();
        let mut bucket = TokenBucket::new(
            RateLimitConfig {
                burst: 1,
                per_second: 100.0,
            },
            t0,
        );
        assert!(bucket.try_acquire(t0));
        // A `now` in the past accrues nothing (saturating), so still throttled.
        assert!(!bucket.try_acquire(t0));
    }

    #[test]
    fn backpressure_disconnect_maps_to_close_code() {
        assert_eq!(BackpressureDisconnect::SlowConsumer.ws_close_code(), 1013);
        assert_eq!(
            BackpressureDisconnect::SlowConsumer.as_str(),
            "slow_consumer"
        );
    }
}
