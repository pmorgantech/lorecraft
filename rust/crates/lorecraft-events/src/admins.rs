//! `AdminRegistry` — the Rust-owned registry of push-only admin-console
//! connections, a sibling to the player-keyed [`ConnectionRegistry`].
//!
//! The admin channel (`/admin/ws`) is **push-only and not player-scoped**: Python's
//! `AdminBroadcaster.push` fans one opaque frame out to *every* connected admin
//! socket (`webui/admin/websocket.py`). Phase 3c moves that onto the gateway, and
//! (per the resolved admin-push design in `lorecraft-protocol::gateway`) admin
//! lifecycle is **Rust-local** — Python is never told about admin connect/disconnect.
//! So this registry, unlike the player one, tracks no room or player id: an admin
//! entry is only an outbound sender plus the same backpressure treatment every
//! connection gets ([`Conn`]).
//!
//! Each admin is keyed by a monotonically assigned [`AdminId`] the server holds to
//! deregister on socket close. Iteration is over a [`BTreeMap`], so admin fan-out is
//! deterministic (ascending registration order) — matching the sorted-read
//! discipline the player registry keeps.

use std::collections::BTreeMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, RwLock};

use crate::connections::{Conn, OutboundSender};

/// A stable, Rust-local handle to a registered admin connection. Assigned at
/// [`AdminRegistry::register`] time and used to [`AdminRegistry::deregister`] on
/// socket close and to name an admin recipient in a dispatch report.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct AdminId(pub u64);

/// The registry of connected admin consoles.
#[derive(Default)]
pub struct AdminRegistry {
    inner: RwLock<BTreeMap<u64, Arc<Conn>>>,
    next_id: AtomicU64,
}

impl AdminRegistry {
    /// Create an empty admin registry.
    pub fn new() -> Self {
        Self::default()
    }

    /// Register an admin connection's outbound sender, returning the [`AdminId`] the
    /// caller uses to deregister it later. Called by the server *after* an accepted
    /// `AdminAuthResult` handshake.
    pub fn register(&self, sender: OutboundSender) -> AdminId {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        self.inner
            .write()
            .expect("admin registry lock poisoned")
            .insert(id, Arc::new(Conn::new(sender)));
        AdminId(id)
    }

    /// Remove an admin connection, returning whether it was present. Dropping the
    /// stored [`Conn`] (and thus its sender, once no in-flight fan-out holds a clone)
    /// closes the bounded channel, which the writer task observes as end-of-stream.
    pub fn deregister(&self, id: AdminId) -> bool {
        self.inner
            .write()
            .expect("admin registry lock poisoned")
            .remove(&id.0)
            .is_some()
    }

    /// Number of connected admin consoles.
    pub fn count(&self) -> usize {
        self.inner
            .read()
            .expect("admin registry lock poisoned")
            .len()
    }

    /// Whether the given admin is still registered.
    pub fn is_connected(&self, id: AdminId) -> bool {
        self.inner
            .read()
            .expect("admin registry lock poisoned")
            .contains_key(&id.0)
    }

    /// Snapshot of every connected admin, in ascending [`AdminId`] order, as cheap
    /// [`Arc`] clones. Used by `dispatch` to fan a payload out to all admins without
    /// holding the registry lock across the (non-blocking) relay.
    pub(crate) fn connections(&self) -> Vec<(AdminId, Arc<Conn>)> {
        self.inner
            .read()
            .expect("admin registry lock poisoned")
            .iter()
            .map(|(id, conn)| (AdminId(*id), Arc::clone(conn)))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::outbound_channel;
    use crate::DEFAULT_OUTBOUND_QUEUE_DEPTH;

    #[test]
    fn register_assigns_ascending_ids_and_deregister_removes() {
        let reg = AdminRegistry::new();
        let (tx0, _rx0) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        let (tx1, _rx1) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        let a0 = reg.register(tx0);
        let a1 = reg.register(tx1);
        assert_eq!(a0, AdminId(0));
        assert_eq!(a1, AdminId(1));
        assert_eq!(reg.count(), 2);
        assert!(reg.is_connected(a0));

        assert!(reg.deregister(a0));
        assert!(!reg.deregister(a0), "double-deregister is a no-op");
        assert!(!reg.is_connected(a0));
        assert_eq!(reg.count(), 1);
    }

    #[test]
    fn connections_snapshot_is_ordered_by_id() {
        let reg = AdminRegistry::new();
        let (tx0, _rx0) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        let (tx1, _rx1) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        let (tx2, _rx2) = outbound_channel(DEFAULT_OUTBOUND_QUEUE_DEPTH);
        let a0 = reg.register(tx0);
        let a1 = reg.register(tx1);
        let a2 = reg.register(tx2);
        reg.deregister(a1);
        let ids: Vec<AdminId> = reg.connections().into_iter().map(|(id, _)| id).collect();
        assert_eq!(ids, vec![a0, a2]);
    }
}
