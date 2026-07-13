//! Fan-out dispatch — resolve a [`DeliveryDirective`] against the
//! [`ConnectionRegistry`] into a concrete recipient list, then relay the opaque
//! payload into each recipient's **bounded** outbound queue.
//!
//! ## The core improvement over Python
//!
//! Python's `ConnectionManager.broadcast_to_room` / `broadcast_global` do a
//! sequential `for recipient in ...: await send_to_player(...)` loop, so a single
//! slow socket head-of-line-blocks delivery to every co-recipient. Here fan-out
//! is **non-blocking**: each recipient is served with [`mpsc::Sender::try_send`],
//! which never awaits. A recipient whose bounded queue is full (a slow client)
//! yields an immediately-recorded failure and does **not** delay delivery to any
//! sibling recipient. This is the property design decision 9/10 calls out ("one
//! blocked queue doesn't stall a co-recipient") and the foundation `backpressure`
//! (task 3c) will extend with a sustained-overflow disconnect policy.
//!
//! ## Failures are never silent
//!
//! A `try_send` failure is surfaced, not swallowed. `lorecraft-events` has no
//! logging framework dependency (keeping the mechanism dep-light and headless-
//! testable), so instead of emitting a `tracing::warn!` here, every fan-out
//! returns a [`DispatchReport`] enumerating each real failure ([`SendError::Full`]
//! / [`SendError::Closed`]) with the offending [`PlayerId`]. The caller
//! (`lorecraft-server`, task 4) logs the report and — per decision 10 — the
//! `backpressure` policy layer (task 3c) decides when repeated failures warrant
//! dropping the connection. A directive to a player with no live connection is a
//! harmless no-op (counted in [`DispatchReport::skipped_absent`]), exactly
//! matching Python `send_to_player` returning when `ws is None`.

use lorecraft_protocol::gateway::{DeliveryDirective, DeliveryTarget};
use lorecraft_protocol::PlayerId;
use tokio::sync::mpsc;

use crate::connections::{ConnectionRegistry, OutboundPayload, OutboundSender};

/// Default depth of a per-connection bounded outbound queue.
///
/// A static operational tunable this phase (design decision 12) — not a
/// game-balance dial, so it does **not** use the live-tunable `WorldClock`
/// pattern. It is flagged as a candidate *operational* live-tunable later; for
/// now it is a named constant rather than a magic number inlined at each channel
/// construction site.
pub const DEFAULT_OUTBOUND_QUEUE_DEPTH: usize = 256;

/// Construct a bounded outbound channel of the given depth. The sender is handed
/// to [`ConnectionRegistry::register`]; the receiver is drained by the
/// connection's writer task (owned by `lorecraft-server`, task 4).
pub fn outbound_channel(depth: usize) -> (OutboundSender, mpsc::Receiver<OutboundPayload>) {
    mpsc::channel(depth)
}

/// Why a single recipient's relay failed. Both variants are *real* failures worth
/// recording (a slow or dead client); an absent connection is not an error and is
/// tracked separately in [`DispatchReport::skipped_absent`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SendError {
    /// The recipient's bounded queue was full — a slow client not draining fast
    /// enough. (Python's player path has no equivalent; this is new protective
    /// behavior per design decision 10.)
    Full,
    /// The recipient's channel was closed (its writer task/receiver was dropped) —
    /// a dead connection. Analogous to Python's failed `send_json` that triggers a
    /// connection drop.
    Closed,
}

/// A per-recipient relay failure, pairing the offending player with the reason.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeliveryFailure {
    /// The recipient whose relay failed.
    pub player_id: PlayerId,
    /// Why it failed.
    pub error: SendError,
}

/// The outcome of resolving and relaying one [`DeliveryDirective`]. Deliberately
/// non-silent: the caller inspects `failures` to log and (later, in task 3c)
/// apply a disconnect policy.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct DispatchReport {
    /// Number of recipients the payload was successfully queued for.
    pub delivered: usize,
    /// Recipients skipped because they had no live connection — harmless no-ops.
    pub skipped_absent: usize,
    /// Real relay failures (full or closed queues), never silent.
    pub failures: Vec<DeliveryFailure>,
}

impl DispatchReport {
    /// Whether every resolved recipient was either delivered to or a harmless
    /// no-op (i.e. no real send failure occurred).
    pub fn is_clean(&self) -> bool {
        self.failures.is_empty()
    }
}

/// Resolve `directive.target`/`directive.exclude` against `registry` and relay
/// `directive.payload` to each recipient with a non-blocking `try_send`.
///
/// Recipient resolution mirrors the Python fan-out targets:
/// - [`DeliveryTarget::Player`] → that single player,
/// - [`DeliveryTarget::Room`] → [`ConnectionRegistry::players_in_room`] (sorted),
/// - [`DeliveryTarget::Global`] → [`ConnectionRegistry::connected_player_ids`]
///   (sorted).
///
/// [`DeliveryTarget::Admin`] is a **placeholder no-op here** — admin fan-out
/// resolves against a separate admin registry that Phase 3c task 2 wires in;
/// `ConnectionRegistry` is player-keyed and has no admin sockets, so this arm
/// currently resolves to zero recipients. Task 2 replaces it with real admin
/// fan-out (register on admin socket connect, deregister on close).
///
/// The `exclude` player (e.g. the actor who caused a broadcast) is omitted.
pub fn dispatch(registry: &ConnectionRegistry, directive: &DeliveryDirective) -> DispatchReport {
    let recipients: Vec<PlayerId> = match &directive.target {
        DeliveryTarget::Player { id } => vec![id.clone()],
        DeliveryTarget::Room { id } => registry.players_in_room(id),
        DeliveryTarget::Global => registry.connected_player_ids(),
        // TODO(phase3c-task2): resolve against the admin registry once it exists.
        DeliveryTarget::Admin => Vec::new(),
    };

    let mut report = DispatchReport::default();
    for recipient in recipients {
        if directive.exclude.as_ref() == Some(&recipient) {
            continue;
        }
        match relay(registry, &recipient, directive.payload.clone()) {
            RelayOutcome::Delivered => report.delivered += 1,
            RelayOutcome::Absent => report.skipped_absent += 1,
            RelayOutcome::Failed(error) => report.failures.push(DeliveryFailure {
                player_id: recipient,
                error,
            }),
        }
    }
    report
}

/// The result of relaying to one recipient.
enum RelayOutcome {
    Delivered,
    Absent,
    Failed(SendError),
}

/// Non-blocking relay of one payload to one recipient. Clones the sender out from
/// under the registry read lock, then `try_send`s with the lock released so a full
/// or slow queue can never hold the shared map.
fn relay(
    registry: &ConnectionRegistry,
    player_id: &PlayerId,
    payload: OutboundPayload,
) -> RelayOutcome {
    let Some(sender) = registry.sender_for(player_id) else {
        return RelayOutcome::Absent;
    };
    match sender.try_send(payload) {
        Ok(()) => RelayOutcome::Delivered,
        Err(mpsc::error::TrySendError::Full(_)) => RelayOutcome::Failed(SendError::Full),
        Err(mpsc::error::TrySendError::Closed(_)) => RelayOutcome::Failed(SendError::Closed),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::Arc;
    use std::time::Duration;

    fn pid(s: &str) -> PlayerId {
        PlayerId(s.into())
    }

    fn room_directive(room: &str, exclude: Option<&str>) -> DeliveryDirective {
        DeliveryDirective {
            target: DeliveryTarget::Room { id: room.into() },
            exclude: exclude.map(|s| PlayerId(s.into())),
            payload: json!({"type": "feed_append", "text": "hi"}),
        }
    }

    #[test]
    fn broadcast_to_room_resolves_sorted_membership_and_respects_exclude() {
        let reg = ConnectionRegistry::new();
        // Keep receivers alive so channels stay open and drainable.
        let (tx_c, mut rx_c) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        let (tx_a, mut rx_a) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        let (tx_b, mut rx_b) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        reg.register(pid("charlie"), tx_c, Some("hall".into()));
        reg.register(pid("alice"), tx_a, Some("hall".into()));
        reg.register(pid("bob"), tx_b, Some("hall".into()));

        // Exclude alice (the actor). bob + charlie should receive.
        let report = dispatch(&reg, &room_directive("hall", Some("alice")));

        assert_eq!(report.delivered, 2);
        assert_eq!(report.skipped_absent, 0);
        assert!(report.is_clean());
        // Excluded actor received nothing.
        assert!(rx_a.try_recv().is_err());
        // Both non-excluded recipients received the payload.
        assert!(rx_b.try_recv().is_ok());
        assert!(rx_c.try_recv().is_ok());
    }

    #[test]
    fn player_target_delivers_to_single_recipient() {
        let reg = ConnectionRegistry::new();
        let (tx, mut rx) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        reg.register(pid("solo"), tx, Some("void".into()));

        let directive = DeliveryDirective {
            target: DeliveryTarget::Player { id: pid("solo") },
            exclude: None,
            payload: json!({"type": "state_change"}),
        };
        let report = dispatch(&reg, &directive);
        assert_eq!(report.delivered, 1);
        assert!(rx.try_recv().is_ok());
    }

    #[test]
    fn directive_to_absent_player_is_harmless_noop() {
        let reg = ConnectionRegistry::new();
        let directive = DeliveryDirective {
            target: DeliveryTarget::Player { id: pid("nobody") },
            exclude: None,
            payload: json!({"type": "feed_append"}),
        };
        let report = dispatch(&reg, &directive);
        assert_eq!(report.delivered, 0);
        assert_eq!(report.skipped_absent, 1);
        assert!(report.is_clean());
    }

    #[test]
    fn global_target_broadcasts_to_every_connection() {
        let reg = ConnectionRegistry::new();
        let (tx1, _rx1) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        let (tx2, _rx2) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        reg.register(pid("p1"), tx1, Some("r1".into()));
        reg.register(pid("p2"), tx2, Some("r2".into()));

        let directive = DeliveryDirective {
            target: DeliveryTarget::Global,
            exclude: None,
            payload: json!({"type": "clock_tick"}),
        };
        let report = dispatch(&reg, &directive);
        assert_eq!(report.delivered, 2);
        assert!(report.is_clean());
    }

    /// THE HEADLINE CONCURRENCY PROOF (design decision 9/10): one recipient's
    /// bounded queue is full and never drained, while a sibling recipient's queue
    /// is drained by a live consumer task. The fan-out to the sibling must still
    /// complete and succeed — it is NOT stalled by the full queue, because
    /// `try_send` never blocks/awaits.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn full_queue_does_not_stall_co_recipient() {
        let reg = Arc::new(ConnectionRegistry::new());

        // Slow client: queue depth 1, receiver held but NEVER drained → the queue
        // fills and stays full.
        let (tx_slow, _rx_slow_never_drained) = outbound_channel(1);
        reg.register(pid("slow"), tx_slow, Some("plaza".into()));

        // Fast client: a live consumer task drains its queue and signals receipt.
        let (tx_fast, mut rx_fast) = outbound_channel(1);
        reg.register(pid("fast"), tx_fast, Some("plaza".into()));

        // Pre-fill the slow client's single slot so its next try_send is Full.
        // (Do it through the registry the same way dispatch will.)
        let pre = dispatch(
            &reg,
            &DeliveryDirective {
                target: DeliveryTarget::Player { id: pid("slow") },
                exclude: None,
                payload: json!({"seq": 0}),
            },
        );
        assert_eq!(pre.delivered, 1); // slot now occupied, not drained

        // Spawn the fast client's consumer; it reports the first payload it drains.
        let (got_tx, got_rx) = tokio::sync::oneshot::channel();
        let consumer = tokio::spawn(async move {
            if let Some(msg) = rx_fast.recv().await {
                let _ = got_tx.send(msg);
            }
        });

        // Fan out a room broadcast. `slow` is full (never drained); `fast` is live.
        let report = dispatch(&reg, &room_directive("plaza", None));

        // The sibling delivery succeeded and the full queue is a recorded failure
        // — but crucially the sibling was reached, not blocked behind the stall.
        assert_eq!(report.delivered, 1, "fast recipient must be delivered to");
        assert_eq!(
            report.failures,
            vec![DeliveryFailure {
                player_id: pid("slow"),
                error: SendError::Full,
            }],
            "slow recipient's full queue is a recorded, non-silent failure"
        );

        // Prove the fast consumer actually received the broadcast payload, quickly,
        // despite the slow client's queue being permanently full.
        let received = tokio::time::timeout(Duration::from_secs(2), got_rx)
            .await
            .expect("fast recipient should receive without being stalled")
            .expect("consumer task delivered a payload");
        assert_eq!(received, json!({"type": "feed_append", "text": "hi"}));

        consumer.await.expect("consumer task joins cleanly");
    }

    #[test]
    fn closed_queue_is_recorded_as_failure() {
        let reg = ConnectionRegistry::new();
        let (tx, rx) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        reg.register(pid("gone"), tx, Some("room".into()));
        // Drop the receiver: the channel is now closed.
        drop(rx);

        let report = dispatch(
            &reg,
            &DeliveryDirective {
                target: DeliveryTarget::Player { id: pid("gone") },
                exclude: None,
                payload: json!({"type": "state_change"}),
            },
        );
        assert_eq!(report.delivered, 0);
        assert_eq!(
            report.failures,
            vec![DeliveryFailure {
                player_id: pid("gone"),
                error: SendError::Closed,
            }]
        );
        assert!(!report.is_clean());
    }
}
