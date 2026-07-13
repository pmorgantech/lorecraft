//! Fan-out dispatch — resolve a [`DeliveryDirective`] against the connection
//! registries into a concrete recipient list, then relay the opaque payload into
//! each recipient's **bounded** outbound queue with a non-blocking `try_send`.
//!
//! ## The core improvement over Python
//!
//! Python's `ConnectionManager.broadcast_to_room` / `broadcast_global` do a
//! sequential `for recipient in ...: await send_to_player(...)` loop, so a single
//! slow socket head-of-line-blocks delivery to every co-recipient. Here fan-out is
//! **non-blocking**: each recipient is served with [`mpsc::Sender::try_send`], which
//! never awaits. A recipient whose bounded queue is full (a slow client) yields an
//! immediately-recorded failure and does **not** delay delivery to any sibling
//! recipient (design decision 9).
//!
//! ## Slow-client backpressure (design decision 10)
//!
//! `try_send` alone only *skips* a full queue — it never bounds a consumer that has
//! stopped reading. Phase 3c adds that bound: each connection carries an
//! [`OverflowTracker`](crate::backpressure::OverflowTracker), advanced here on every
//! relay outcome (reset on success, incremented on a full queue). When a
//! connection's consecutive-overflow streak reaches the
//! [`BackpressureConfig`](crate::backpressure::BackpressureConfig) threshold it is
//! added to [`DispatchReport::disconnect`] with
//! [`BackpressureDisconnect::SlowConsumer`], and the server tears it down (mapping
//! the reason to a WS close code). Crucially the tracking is per-connection and
//! lock-free, so signalling one stalled consumer never delays a sibling — the
//! non-blocking property is preserved.
//!
//! ## Failures are never silent
//!
//! Every relay failure is surfaced in a [`DispatchReport`], not swallowed:
//! `lorecraft-events` has no logging framework dependency (keeping the mechanism
//! dep-light and headless-testable), so the caller (`lorecraft-server`) logs the
//! report and acts on `disconnect`. A directive to a player with no live connection
//! is a harmless no-op (counted in [`DispatchReport::skipped_absent`]).

use lorecraft_protocol::gateway::{DeliveryDirective, DeliveryTarget};
use lorecraft_protocol::PlayerId;
use tokio::sync::mpsc;

use crate::admins::AdminId;
use crate::backpressure::{BackpressureConfig, BackpressureDisconnect};
use crate::connections::{Conn, ConnectionRegistry, OutboundFrame, OutboundPayload};

/// Default depth of a per-connection bounded outbound queue.
///
/// A static operational tunable this phase (design decision 12) — not a
/// game-balance dial, so it does **not** use the live-tunable `WorldClock`
/// pattern. It is flagged as a candidate *operational* live-tunable later; for
/// now it is a named constant rather than a magic number inlined at each channel
/// construction site.
pub const DEFAULT_OUTBOUND_QUEUE_DEPTH: usize = 256;

/// Construct a bounded outbound channel of the given depth. The sender is handed
/// to [`ConnectionRegistry::register`]/[`ConnectionRegistry::register_admin`]; the
/// receiver is drained by the connection's writer task (owned by `lorecraft-server`).
pub fn outbound_channel(
    depth: usize,
) -> (
    crate::connections::OutboundSender,
    mpsc::Receiver<OutboundFrame>,
) {
    mpsc::channel(depth)
}

/// A fan-out recipient — a player connection or an admin console. Fan-out failures
/// and slow-consumer disconnect directives are reported against this identity so
/// the caller can act on either connection class uniformly.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Recipient {
    /// A player connection, keyed by [`PlayerId`].
    Player(PlayerId),
    /// An admin console, keyed by its Rust-local [`AdminId`].
    Admin(AdminId),
}

/// Why a single recipient's relay failed. Both variants are *real* failures worth
/// recording (a slow or dead client); an absent player connection is not an error
/// and is tracked separately in [`DispatchReport::skipped_absent`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SendError {
    /// The recipient's bounded queue was full — a slow client not draining fast
    /// enough. Sustained overflow escalates to a [`DispatchReport::disconnect`]
    /// entry.
    Full,
    /// The recipient's channel was closed (its writer task/receiver was dropped) —
    /// a dead connection.
    Closed,
}

/// A per-recipient relay failure, pairing the offending recipient with the reason.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeliveryFailure {
    /// The recipient whose relay failed.
    pub recipient: Recipient,
    /// Why it failed.
    pub error: SendError,
}

/// A gateway-initiated teardown the server must perform: a recipient crossed the
/// slow-consumer threshold and should be disconnected with the given reason.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DisconnectDirective {
    /// The connection to tear down.
    pub recipient: Recipient,
    /// Why (maps to a WS close code via
    /// [`BackpressureDisconnect::ws_close_code`]).
    pub reason: BackpressureDisconnect,
}

/// The outcome of resolving and relaying one [`DeliveryDirective`]. Deliberately
/// non-silent: the caller inspects `failures` to log and `disconnect` to tear down
/// slow consumers.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct DispatchReport {
    /// Number of recipients the payload was successfully queued for.
    pub delivered: usize,
    /// Player recipients skipped because they had no live connection — harmless
    /// no-ops (admins are never counted here; they are resolved from a live set).
    pub skipped_absent: usize,
    /// Real relay failures (full or closed queues), never silent.
    pub failures: Vec<DeliveryFailure>,
    /// Recipients whose sustained overflow crossed the disconnect threshold during
    /// this dispatch and must be torn down. Empty in the common case.
    pub disconnect: Vec<DisconnectDirective>,
}

impl DispatchReport {
    /// Whether every resolved recipient was either delivered to or a harmless
    /// no-op (i.e. no real send failure occurred).
    pub fn is_clean(&self) -> bool {
        self.failures.is_empty()
    }
}

/// Resolve `directive.target`/`directive.exclude` against `registry` and relay
/// `directive.payload` to each recipient with a non-blocking `try_send`, using the
/// default [`BackpressureConfig`].
///
/// Recipient resolution mirrors the Python fan-out targets:
/// - [`DeliveryTarget::Player`] → that single player,
/// - [`DeliveryTarget::Room`] → [`ConnectionRegistry::players_in_room`] (sorted),
/// - [`DeliveryTarget::Global`] → [`ConnectionRegistry::connected_player_ids`]
///   (sorted),
/// - [`DeliveryTarget::Admin`] → every registered admin console (ascending
///   [`AdminId`] order).
///
/// The `exclude` player (e.g. the actor who caused a broadcast) is omitted from the
/// player targets. It is **ignored for `Admin`** fan-out: `exclude` is a
/// [`PlayerId`] and no admin console has one, so the two namespaces never collide.
///
/// `directive.coalesce_key` is **carried** onto each transport
/// [`OutboundFrame`](crate::connections::OutboundFrame) verbatim but never
/// *interpreted* here — the mpsc transport queue cannot itself do keyed
/// replacement, so the actual keep-latest coalescing is the
/// [`CoalescingQueue`](crate::backpressure::CoalescingQueue) mechanism the server
/// folds into its writer drain. Attaching (not reading) the key keeps this function
/// payload-blind while letting the writer honor the policy owner's key.
pub fn dispatch(registry: &ConnectionRegistry, directive: &DeliveryDirective) -> DispatchReport {
    dispatch_with_config(registry, directive, &BackpressureConfig::default())
}

/// [`dispatch`] with an explicit backpressure configuration (the slow-consumer
/// disconnect threshold). The default-config [`dispatch`] delegates here.
pub fn dispatch_with_config(
    registry: &ConnectionRegistry,
    directive: &DeliveryDirective,
    config: &BackpressureConfig,
) -> DispatchReport {
    let mut report = DispatchReport::default();
    let coalesce_key = directive.coalesce_key.as_deref();
    match &directive.target {
        DeliveryTarget::Player { id } => {
            if directive.exclude.as_ref() != Some(id) {
                relay_player(
                    registry,
                    id,
                    &directive.payload,
                    coalesce_key,
                    config,
                    &mut report,
                );
            }
        }
        DeliveryTarget::Room { id } => {
            for pid in registry.players_in_room(id) {
                if directive.exclude.as_ref() == Some(&pid) {
                    continue;
                }
                relay_player(
                    registry,
                    &pid,
                    &directive.payload,
                    coalesce_key,
                    config,
                    &mut report,
                );
            }
        }
        DeliveryTarget::Global => {
            for pid in registry.connected_player_ids() {
                if directive.exclude.as_ref() == Some(&pid) {
                    continue;
                }
                relay_player(
                    registry,
                    &pid,
                    &directive.payload,
                    coalesce_key,
                    config,
                    &mut report,
                );
            }
        }
        DeliveryTarget::Admin => {
            for (admin_id, conn) in registry.admins().connections() {
                relay(
                    Recipient::Admin(admin_id),
                    &conn,
                    directive.payload.clone(),
                    coalesce_key.map(str::to_owned),
                    config,
                    &mut report,
                );
            }
        }
    }
    report
}

/// Resolve one player to a live connection handle and relay, or count it absent.
fn relay_player(
    registry: &ConnectionRegistry,
    player_id: &PlayerId,
    payload: &OutboundPayload,
    coalesce_key: Option<&str>,
    config: &BackpressureConfig,
    report: &mut DispatchReport,
) {
    match registry.conn_for(player_id) {
        None => report.skipped_absent += 1,
        Some(conn) => relay(
            Recipient::Player(player_id.clone()),
            &conn,
            payload.clone(),
            coalesce_key.map(str::to_owned),
            config,
            report,
        ),
    }
}

/// Non-blocking relay of one frame into a resolved connection's bounded queue,
/// advancing its overflow tracker and recording the outcome. The registry lock is
/// already released (the caller cloned the handle out), so a full or dead queue can
/// never hold the shared map and can never delay a sibling recipient. The
/// `coalesce_key` is attached to the transport frame verbatim (never interpreted)
/// for the writer's [`CoalescingQueue`](crate::backpressure::CoalescingQueue).
fn relay(
    recipient: Recipient,
    conn: &Conn,
    payload: OutboundPayload,
    coalesce_key: Option<String>,
    config: &BackpressureConfig,
    report: &mut DispatchReport,
) {
    let frame = OutboundFrame {
        payload,
        coalesce_key,
    };
    match conn.sender.try_send(frame) {
        Ok(()) => {
            conn.overflow.record_success();
            report.delivered += 1;
        }
        Err(mpsc::error::TrySendError::Full(_)) => {
            let tripped = conn.overflow.record_overflow(config);
            report.failures.push(DeliveryFailure {
                recipient: recipient.clone(),
                error: SendError::Full,
            });
            if tripped {
                report.disconnect.push(DisconnectDirective {
                    recipient,
                    reason: BackpressureDisconnect::SlowConsumer,
                });
            }
        }
        Err(mpsc::error::TrySendError::Closed(_)) => report.failures.push(DeliveryFailure {
            recipient,
            error: SendError::Closed,
        }),
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
            coalesce_key: None,
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
        assert!(report.disconnect.is_empty());
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
            coalesce_key: None,
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
            coalesce_key: None,
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
            coalesce_key: None,
        };
        let report = dispatch(&reg, &directive);
        assert_eq!(report.delivered, 2);
        assert!(report.is_clean());
    }

    /// THE HEADLINE CONCURRENCY PROOF (design decision 9): one recipient's bounded
    /// queue is full and never drained, while a sibling recipient's queue is drained
    /// by a live consumer task. The fan-out to the sibling must still complete and
    /// succeed — it is NOT stalled by the full queue, because `try_send` never
    /// blocks/awaits.
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
        let pre = dispatch(
            &reg,
            &DeliveryDirective {
                target: DeliveryTarget::Player { id: pid("slow") },
                exclude: None,
                payload: json!({"seq": 0}),
                coalesce_key: None,
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

        assert_eq!(report.delivered, 1, "fast recipient must be delivered to");
        assert_eq!(
            report.failures,
            vec![DeliveryFailure {
                recipient: Recipient::Player(pid("slow")),
                error: SendError::Full,
            }],
            "slow recipient's full queue is a recorded, non-silent failure"
        );

        let received = tokio::time::timeout(Duration::from_secs(2), got_rx)
            .await
            .expect("fast recipient should receive without being stalled")
            .expect("consumer task delivered a payload");
        assert_eq!(
            received.payload,
            json!({"type": "feed_append", "text": "hi"})
        );

        consumer.await.expect("consumer task joins cleanly");
    }

    /// THE HEADLINE SLOW-CLIENT BACKPRESSURE PROOF (design decision 10): a consumer
    /// that stops draining is *bounded* — marked for disconnect within the
    /// configured consecutive-overflow threshold — while a co-located sibling that
    /// keeps draining receives every single broadcast, unblocked.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn stalled_consumer_is_marked_for_disconnect_without_starving_sibling() {
        let reg = Arc::new(ConnectionRegistry::new());
        // Trip after 3 consecutive overflows — small threshold keeps the test tight.
        let config = BackpressureConfig {
            max_consecutive_overflow: 3,
        };

        // Slow client: depth 1, never drained → overflows on every broadcast after
        // the first.
        let (tx_slow, _rx_slow) = outbound_channel(1);
        reg.register(pid("slow"), tx_slow, Some("plaza".into()));

        // Fast client: a live task drains continuously and counts receipts.
        let (tx_fast, mut rx_fast) = outbound_channel(8);
        reg.register(pid("fast"), tx_fast, Some("plaza".into()));
        let (count_tx, count_rx) = tokio::sync::oneshot::channel();
        let consumer = tokio::spawn(async move {
            let mut n = 0usize;
            let mut count_tx = Some(count_tx);
            // Drain until the channel closes (registry dropped at test end).
            while (rx_fast.recv().await).is_some() {
                n += 1;
                if n == 4 {
                    if let Some(tx) = count_tx.take() {
                        let _ = tx.send(n);
                    }
                }
            }
        });

        // Pre-fill the slow client so subsequent broadcasts overflow it.
        dispatch(
            &reg,
            &DeliveryDirective {
                target: DeliveryTarget::Player { id: pid("slow") },
                exclude: None,
                payload: json!({"seq": "prefill"}),
                coalesce_key: None,
            },
        );

        // Broadcast four times. Overflow streak for `slow`: 1, 2, 3 (trips), 4.
        let mut disconnect_seen_on: Option<usize> = None;
        for i in 0..4 {
            let report = dispatch_with_config(&reg, &room_directive("plaza", None), &config);
            assert_eq!(
                report.delivered, 1,
                "fast is delivered to on every broadcast"
            );
            if let Some(directive) = report.disconnect.first() {
                assert_eq!(
                    *directive,
                    DisconnectDirective {
                        recipient: Recipient::Player(pid("slow")),
                        reason: BackpressureDisconnect::SlowConsumer,
                    }
                );
                disconnect_seen_on.get_or_insert(i);
            }
        }

        // The stalled consumer was signalled exactly at the threshold crossing (the
        // 3rd overflow → the 3rd broadcast, index 2), not before, not repeatedly.
        assert_eq!(
            disconnect_seen_on,
            Some(2),
            "slow consumer marked-for-disconnect within the bounded threshold"
        );

        // The sibling received all four broadcasts, unblocked by the stall.
        let fast_count = tokio::time::timeout(Duration::from_secs(2), count_rx)
            .await
            .expect("fast recipient should receive all four broadcasts")
            .expect("consumer reported its count");
        assert_eq!(fast_count, 4);

        drop(reg);
        consumer.await.expect("consumer task joins cleanly");
    }

    #[test]
    fn admin_target_fans_out_to_all_registered_admins_in_order() {
        let reg = ConnectionRegistry::new();
        let (tx0, mut rx0) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        let (tx1, mut rx1) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        let (tx2, mut rx2) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        let _a0 = reg.register_admin(tx0);
        let a1 = reg.register_admin(tx1);
        let _a2 = reg.register_admin(tx2);
        // A player in a room must NOT receive an admin-targeted push.
        let (txp, mut rxp) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        reg.register(pid("watcher"), txp, Some("plaza".into()));

        // Drop one admin; fan-out must reach exactly the remaining two.
        reg.deregister_admin(a1);

        let directive = DeliveryDirective {
            target: DeliveryTarget::Admin,
            // `exclude` is a PlayerId — irrelevant to admins, must be ignored.
            exclude: Some(pid("watcher")),
            payload: json!({"type": "admin_event", "kind": "player_joined"}),
            coalesce_key: None,
        };
        let report = dispatch(&reg, &directive);

        assert_eq!(
            report.delivered, 2,
            "both surviving admins receive the push"
        );
        assert!(report.is_clean());
        assert!(rx0.try_recv().is_ok());
        assert!(rx1.try_recv().is_err(), "deregistered admin gets nothing");
        assert!(rx2.try_recv().is_ok());
        assert!(rxp.try_recv().is_err(), "player is not an admin recipient");
    }

    #[test]
    fn slow_admin_is_marked_for_disconnect_like_a_player() {
        // Backpressure applies to admin connections too (the exit test's slow client
        // may be an admin console).
        let reg = ConnectionRegistry::new();
        let config = BackpressureConfig {
            max_consecutive_overflow: 2,
        };
        let (tx, _rx_never_drained) = outbound_channel(1);
        let admin = reg.register_admin(tx);

        let directive = DeliveryDirective {
            target: DeliveryTarget::Admin,
            exclude: None,
            payload: json!({"type": "admin_event"}),
            coalesce_key: None,
        };
        // 1st fills the single slot (delivered); 2nd + 3rd overflow; 3rd... no —
        // threshold 2 trips on the 2nd overflow, i.e. the 3rd dispatch.
        dispatch_with_config(&reg, &directive, &config); // delivered, streak reset
        let r2 = dispatch_with_config(&reg, &directive, &config); // overflow streak 1
        assert!(r2.disconnect.is_empty());
        let r3 = dispatch_with_config(&reg, &directive, &config); // overflow streak 2 → trip
        assert_eq!(
            r3.disconnect,
            vec![DisconnectDirective {
                recipient: Recipient::Admin(admin),
                reason: BackpressureDisconnect::SlowConsumer,
            }]
        );
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
                coalesce_key: None,
            },
        );
        assert_eq!(report.delivered, 0);
        assert_eq!(
            report.failures,
            vec![DeliveryFailure {
                recipient: Recipient::Player(pid("gone")),
                error: SendError::Closed,
            }]
        );
        assert!(!report.is_clean());
    }
}
