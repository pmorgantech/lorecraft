//! `disconnect.rs` — the server-side close-propagation seam for slow-client
//! backpressure (Phase 3c, item 3).
//!
//! ## The propagation problem
//!
//! [`dispatch`](lorecraft_events::dispatch) detects a stalled consumer — a
//! connection whose bounded outbound queue overflowed past the
//! [`BackpressureConfig`](lorecraft_events::BackpressureConfig) threshold — and
//! reports it in [`DispatchReport::disconnect`](lorecraft_events::DispatchReport).
//! But `dispatch` runs inside the [`ForwardClient`](crate::forward::ForwardClient)
//! read loop (relaying Python's `Deliver` frames), while the WebSocket sink that
//! must actually be *closed with 1013* is owned by a **different** task — the
//! per-connection writer/handler. The read loop cannot reach across to that socket
//! directly.
//!
//! ## The design: a keyed, level-triggered close signal
//!
//! [`DisconnectHub`] bridges the two. Each connection, at register time, calls
//! [`DisconnectHub::register`] to obtain a [`watch::Receiver<bool>`]; the hub keeps
//! the paired [`watch::Sender`] keyed by the connection's identity. Both the
//! connection's **handler** (its receive loop) and its **writer** hold a clone of
//! that receiver and `select!` on it. When any `dispatch` call — on *any* forward
//! link, since fan-out targets the shared registry — returns a disconnect directive
//! for that recipient, the read loop calls [`DisconnectHub::trigger`], which flips
//! the watch to `true`. That wakes:
//!
//! - the **writer**, which closes the WS with code `1013` and exits, and
//! - the **handler**, which breaks its receive loop and runs normal teardown
//!   (deregister + Python `Disconnected` notify for players).
//!
//! A [`watch`] channel is chosen deliberately over a bare
//! [`Notify`](tokio::sync::Notify): it is **level-triggered and multi-consumer**, so
//! a single trigger reliably wakes *both* the handler and the writer with no
//! notify-before-await race (a `Notify` permit only wakes one waiter). Because the
//! signal is a value, a trigger that lands before a task starts awaiting is still
//! observed via the version bump — there is no lost-wakeup window.
//!
//! Crucially, triggering is a non-blocking `watch::Sender::send` under a short
//! mutex: signalling one stalled consumer never blocks the read loop and never
//! delays delivery to a co-located, well-behaved sibling (design decision 9's
//! non-blocking property is preserved end to end).

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use lorecraft_events::{
    AdminId, BackpressureConfig, ConnectionRegistry, DisconnectDirective, Recipient,
};
use lorecraft_protocol::ids::PlayerId;
use tokio::sync::watch;

/// A hashable, owned key identifying one connection in the [`DisconnectHub`] map.
///
/// [`Recipient`] itself is not `Hash` (and carries clonable id payloads), so this
/// small local enum mirrors its two variants with owned, hashable contents.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
enum ConnKey {
    /// A player connection, keyed by its raw player-id string.
    Player(String),
    /// An admin console, keyed by its Rust-local numeric id.
    Admin(u64),
}

impl ConnKey {
    /// The map key for a fan-out [`Recipient`].
    fn of(recipient: &Recipient) -> Self {
        match recipient {
            Recipient::Player(id) => ConnKey::Player(id.0.clone()),
            Recipient::Admin(id) => ConnKey::Admin(id.0),
        }
    }
}

/// The server-owned registry of per-connection close signals (see the module docs).
///
/// Shared (behind an [`Arc`]) across every [`ForwardClient`](crate::forward) so a
/// disconnect directive detected while relaying on one link can close a stalled
/// connection served by any other. Cheap to clone (an `Arc`).
#[derive(Default)]
pub struct DisconnectHub {
    inner: Mutex<HashMap<ConnKey, watch::Sender<bool>>>,
}

impl DisconnectHub {
    /// Create an empty hub.
    pub fn new() -> Self {
        Self::default()
    }

    /// Register a close signal for `recipient`, returning the receiver the
    /// connection's writer + handler tasks `select!` on. Re-registering the same
    /// recipient replaces the previous signal (a benign reconnect race).
    pub fn register(&self, recipient: &Recipient) -> watch::Receiver<bool> {
        let (tx, rx) = watch::channel(false);
        self.inner
            .lock()
            .expect("disconnect hub lock poisoned")
            .insert(ConnKey::of(recipient), tx);
        rx
    }

    /// Remove `recipient`'s close signal (called from the connection's teardown,
    /// symmetric with [`ConnectionRegistry::deregister`]). Dropping the stored
    /// sender is harmless: its receivers observe end-of-stream, but by teardown the
    /// tasks holding them are already exiting.
    pub fn deregister(&self, recipient: &Recipient) {
        self.inner
            .lock()
            .expect("disconnect hub lock poisoned")
            .remove(&ConnKey::of(recipient));
    }

    /// Fire the close signal for one dispatch-reported [`DisconnectDirective`]. A
    /// non-blocking [`watch::Sender::send`] under a short lock; if the recipient is
    /// already gone (concurrent teardown) it is a no-op. Never blocks the read loop.
    pub fn trigger(&self, directive: &DisconnectDirective) {
        if let Some(tx) = self
            .inner
            .lock()
            .expect("disconnect hub lock poisoned")
            .get(&ConnKey::of(&directive.recipient))
        {
            // A closed receiver (task already exited) makes this Err — ignored.
            let _ = tx.send(true);
        }
    }

    /// Number of connections currently holding a close signal (tests/diagnostics).
    pub fn len(&self) -> usize {
        self.inner
            .lock()
            .expect("disconnect hub lock poisoned")
            .len()
    }

    /// Whether the hub tracks no connections.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

/// The shared dispatch context threaded into every [`ForwardClient`](crate::forward).
///
/// Bundles the three things a forward link's read loop needs to fan a Python
/// `Deliver`/`CommandReply` out and enforce backpressure: the authoritative
/// [`ConnectionRegistry`], the [`DisconnectHub`] it triggers on a slow-consumer
/// overflow, and the operational [`BackpressureConfig`] (the disconnect threshold).
/// Cheaply cloneable — the registry and hub are `Arc`, the config is `Copy`.
#[derive(Clone)]
pub struct DispatchContext {
    /// The authoritative connection/room map fan-out resolves against.
    pub registry: Arc<ConnectionRegistry>,
    /// The close-signal hub triggered on a slow-consumer disconnect directive.
    pub disconnect: Arc<DisconnectHub>,
    /// The operational slow-client disconnect threshold.
    pub backpressure: BackpressureConfig,
}

impl DispatchContext {
    /// Build a context from its parts.
    pub fn new(
        registry: Arc<ConnectionRegistry>,
        disconnect: Arc<DisconnectHub>,
        backpressure: BackpressureConfig,
    ) -> Self {
        Self {
            registry,
            disconnect,
            backpressure,
        }
    }
}

/// Helper: build the [`Recipient`] naming a player connection.
pub(crate) fn player_recipient(player_id: &PlayerId) -> Recipient {
    Recipient::Player(player_id.clone())
}

/// Helper: build the [`Recipient`] naming an admin console.
pub(crate) fn admin_recipient(id: AdminId) -> Recipient {
    Recipient::Admin(id)
}

#[cfg(test)]
mod tests {
    use super::*;
    use lorecraft_events::BackpressureDisconnect;

    fn slow(recipient: Recipient) -> DisconnectDirective {
        DisconnectDirective {
            recipient,
            reason: BackpressureDisconnect::SlowConsumer,
        }
    }

    #[test]
    fn trigger_flips_the_registered_signal_for_the_right_recipient() {
        let hub = DisconnectHub::new();
        let player = PlayerId("hero".into());
        let rx = hub.register(&player_recipient(&player));
        assert!(!*rx.borrow(), "starts unset");
        assert_eq!(hub.len(), 1);

        // Triggering a *different* recipient must not flip this signal.
        hub.trigger(&slow(admin_recipient(AdminId(7))));
        assert!(!*rx.borrow());

        hub.trigger(&slow(player_recipient(&player)));
        assert!(*rx.borrow(), "the matching recipient's signal is set");
    }

    #[test]
    fn deregister_removes_the_signal_and_trigger_becomes_a_noop() {
        let hub = DisconnectHub::new();
        let admin = admin_recipient(AdminId(3));
        let rx = hub.register(&admin);
        hub.deregister(&admin);
        assert!(hub.is_empty());
        // Triggering a removed recipient is a harmless no-op (does not panic).
        hub.trigger(&slow(admin));
        // The receiver still reads its last value (unset) — nothing set it.
        assert!(!*rx.borrow());
    }

    #[test]
    fn trigger_before_await_is_observed_via_the_watch_version() {
        // The level-triggered guarantee: a trigger that lands before the consumer
        // awaits is still seen (no lost wakeup), unlike a bare Notify permit.
        let hub = DisconnectHub::new();
        let player = PlayerId("late".into());
        let mut rx = hub.register(&player_recipient(&player));
        hub.trigger(&slow(player_recipient(&player)));
        // A consumer that only now inspects the signal still sees it set.
        assert!(rx.has_changed().unwrap());
        assert!(*rx.borrow_and_update());
    }
}
