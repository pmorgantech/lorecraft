//! `ConnectionRegistry` — the authoritative Rust-side connection map.
//!
//! This is the Rust-owned mechanism that replaces Python's in-memory
//! `ConnectionManager` (`src/lorecraft/engine/game/connection_manager.py`). It
//! tracks three logical maps, mirroring the Python reference semantics:
//!
//! - `player -> outbound channel handle` (the `mpsc::Sender` `dispatch` feeds),
//! - `player -> current room id`,
//! - `room -> set of players`.
//!
//! All read methods (`players_in_room`, `occupied_rooms`, `connected_player_ids`)
//! return **sorted** results: the existing system relies on this deterministic
//! ordering, so we reproduce Python's `sorted()` discipline exactly. Room
//! membership is stored in a [`BTreeSet`] so per-room reads are sorted for free.
//!
//! The registry is `Send + Sync` and guarded by a single [`RwLock`] because it is
//! shared across concurrent per-connection tasks in `lorecraft-server` (task 4).
//! Room ids are plain `String` — there is no `RoomId` newtype in the protocol
//! crate (see `lorecraft-protocol::gateway` module docs).

use std::collections::{BTreeSet, HashMap};
use std::sync::RwLock;

use lorecraft_protocol::PlayerId;
use tokio::sync::mpsc;

/// The opaque outbound payload relayed to a connection. It is the legacy frame
/// carried verbatim by `DeliveryDirective.payload`; the registry never inspects
/// it (see `lorecraft-protocol::gateway`).
pub type OutboundPayload = serde_json::Value;

/// The sender half of a connection's bounded outbound queue. `dispatch` pushes
/// payloads into it with `try_send`; the draining writer task lives in
/// `lorecraft-server` (task 4).
pub type OutboundSender = mpsc::Sender<OutboundPayload>;

/// The three connection maps, guarded together so lifecycle mutations stay
/// consistent under concurrency.
#[derive(Default)]
struct Inner {
    /// `player -> outbound sender`.
    connections: HashMap<String, OutboundSender>,
    /// `player -> current room id`.
    player_rooms: HashMap<String, String>,
    /// `room -> sorted set of players`.
    room_players: HashMap<String, BTreeSet<String>>,
}

/// The authoritative Rust-side connection + room-membership map.
#[derive(Default)]
pub struct ConnectionRegistry {
    inner: RwLock<Inner>,
}

impl ConnectionRegistry {
    /// Create an empty registry.
    pub fn new() -> Self {
        Self::default()
    }

    /// Register a connection's outbound sender and (optionally) place it in a
    /// room. Mirrors Python `ConnectionManager.connect`: when a room is given it
    /// runs the same move reconciliation as [`move_player`](Self::move_player),
    /// using the player's currently-tracked room as `from` — this handles the
    /// "was in room A but the map says room B" edge case at connect time.
    ///
    /// Re-registering an already-known player replaces the stored sender.
    pub fn register(&self, player_id: PlayerId, sender: OutboundSender, room_id: Option<String>) {
        let mut inner = self.inner.write().expect("registry lock poisoned");
        inner.connections.insert(player_id.0.clone(), sender);
        if let Some(room) = room_id {
            let from = inner.player_rooms.get(&player_id.0).cloned();
            Self::apply_move(&mut inner, &player_id.0, from.as_deref(), &room);
        }
    }

    /// Remove a connection from both the player map and its room's set, returning
    /// the removed outbound sender if the player was connected. Mirrors Python
    /// `ConnectionManager.disconnect`. Dropping the returned sender closes the
    /// bounded channel, which the writer task observes as end-of-stream.
    pub fn deregister(&self, player_id: &PlayerId) -> Option<OutboundSender> {
        let mut inner = self.inner.write().expect("registry lock poisoned");
        let sender = inner.connections.remove(&player_id.0);
        if let Some(room) = inner.player_rooms.remove(&player_id.0) {
            if let Some(players) = inner.room_players.get_mut(&room) {
                players.remove(&player_id.0);
            }
        }
        sender
    }

    /// Move a player from `from_room` to `to_room`, keeping the `player -> room`
    /// and `room -> players` maps consistent. Mirrors Python
    /// `ConnectionManager.move_player`, **including** the reconciliation case: if
    /// the map's currently-tracked room differs from the caller-supplied
    /// `from_room`, the player is discarded from *both* rooms before being added
    /// to `to_room`, so a stale `from_room` cannot leave the player lingering in
    /// two rooms.
    pub fn move_player(&self, player_id: &PlayerId, from_room: Option<&str>, to_room: &str) {
        let mut inner = self.inner.write().expect("registry lock poisoned");
        Self::apply_move(&mut inner, &player_id.0, from_room, to_room);
    }

    /// The shared move mechanism, operating on an already-held write guard so
    /// [`register`](Self::register) can insert and move under a single lock.
    ///
    /// Empty `from_room`/current-room strings are treated as "unset" to match
    /// Python's truthiness checks (`if from_room:` / `if current_room and ...`).
    fn apply_move(inner: &mut Inner, player_id: &str, from_room: Option<&str>, to_room: &str) {
        // Discard from the caller-supplied origin room.
        if let Some(from) = from_room.filter(|room| !room.is_empty()) {
            if let Some(players) = inner.room_players.get_mut(from) {
                players.remove(player_id);
            }
        }
        // Reconcile: if the map thinks the player is somewhere else, discard there
        // too (the "was in room A but map says room B" edge case).
        let current = inner.player_rooms.get(player_id).cloned();
        if let Some(current) = current.filter(|room| !room.is_empty()) {
            if Some(current.as_str()) != from_room {
                if let Some(players) = inner.room_players.get_mut(&current) {
                    players.remove(player_id);
                }
            }
        }
        inner
            .player_rooms
            .insert(player_id.to_string(), to_room.to_string());
        inner
            .room_players
            .entry(to_room.to_string())
            .or_default()
            .insert(player_id.to_string());
    }

    /// Clone the outbound sender for a player, if connected. Used by `dispatch`
    /// to resolve a recipient into a concrete channel handle without holding the
    /// registry lock across the (non-blocking) `try_send`.
    pub(crate) fn sender_for(&self, player_id: &PlayerId) -> Option<OutboundSender> {
        let inner = self.inner.read().expect("registry lock poisoned");
        inner.connections.get(&player_id.0).cloned()
    }

    /// Players currently in `room_id`, **sorted**. Mirrors Python
    /// `players_in_room`; membership is a [`BTreeSet`] so it is already ordered.
    pub fn players_in_room(&self, room_id: &str) -> Vec<PlayerId> {
        let inner = self.inner.read().expect("registry lock poisoned");
        inner
            .room_players
            .get(room_id)
            .map(|players| players.iter().map(|p| PlayerId(p.clone())).collect())
            .unwrap_or_default()
    }

    /// Rooms with at least one connected player, **sorted**. Mirrors Python
    /// `occupied_rooms` — empty room sets (which can linger after everyone leaves)
    /// are filtered out so a world-level broadcast only touches rooms with an
    /// audience.
    pub fn occupied_rooms(&self) -> Vec<String> {
        let inner = self.inner.read().expect("registry lock poisoned");
        let mut rooms: Vec<String> = inner
            .room_players
            .iter()
            .filter(|(_, players)| !players.is_empty())
            .map(|(room, _)| room.clone())
            .collect();
        rooms.sort();
        rooms
    }

    /// Every currently-connected player, **sorted**. Mirrors Python
    /// `connected_player_ids` — the whole-server recipient set for global fan-out.
    pub fn connected_player_ids(&self) -> Vec<PlayerId> {
        let inner = self.inner.read().expect("registry lock poisoned");
        let mut ids: Vec<String> = inner.connections.keys().cloned().collect();
        ids.sort();
        ids.into_iter().map(PlayerId).collect()
    }

    /// Whether the player currently has a live connection. Mirrors Python
    /// `is_connected`.
    pub fn is_connected(&self, player_id: &PlayerId) -> bool {
        let inner = self.inner.read().expect("registry lock poisoned");
        inner.connections.contains_key(&player_id.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pid(s: &str) -> PlayerId {
        PlayerId(s.into())
    }

    /// Convenience: an unbounded-enough channel whose receiver is kept alive by
    /// the returned guard so the sender stays open for the duration of a test.
    fn open_channel() -> (OutboundSender, mpsc::Receiver<OutboundPayload>) {
        mpsc::channel(8)
    }

    #[test]
    fn join_leave_move_updates_all_maps_sorted() {
        let reg = ConnectionRegistry::new();
        let (tx_b, _rx_b) = open_channel();
        let (tx_a, _rx_a) = open_channel();

        // Register out of sorted order to prove reads sort.
        reg.register(pid("bravo"), tx_b, Some("tavern".into()));
        reg.register(pid("alpha"), tx_a, Some("tavern".into()));

        assert_eq!(
            reg.players_in_room("tavern"),
            vec![pid("alpha"), pid("bravo")]
        );
        assert_eq!(reg.occupied_rooms(), vec!["tavern".to_string()]);
        assert_eq!(reg.connected_player_ids(), vec![pid("alpha"), pid("bravo")]);
        assert!(reg.is_connected(&pid("alpha")));

        // Move bravo out to the square.
        reg.move_player(&pid("bravo"), Some("tavern"), "square");

        assert_eq!(reg.players_in_room("tavern"), vec![pid("alpha")]);
        assert_eq!(reg.players_in_room("square"), vec![pid("bravo")]);
        assert_eq!(
            reg.occupied_rooms(),
            vec!["square".to_string(), "tavern".to_string()]
        );

        // Deregister alpha; tavern becomes empty and drops out of occupied_rooms.
        let removed = reg.deregister(&pid("alpha"));
        assert!(removed.is_some());
        assert!(!reg.is_connected(&pid("alpha")));
        assert!(reg.players_in_room("tavern").is_empty());
        assert_eq!(reg.occupied_rooms(), vec!["square".to_string()]);
        assert_eq!(reg.connected_player_ids(), vec![pid("bravo")]);
    }

    #[test]
    fn move_player_reconciles_stale_from_room() {
        // The edge case Python guards: caller passes a `from_room` that does not
        // match the map's actual tracked room. The player must not end up counted
        // in two rooms.
        let reg = ConnectionRegistry::new();
        let (tx, _rx) = open_channel();
        reg.register(pid("wanderer"), tx, Some("room-a".into()));
        assert_eq!(reg.players_in_room("room-a"), vec![pid("wanderer")]);

        // Move with a STALE from_room ("room-b") while the map says "room-a".
        reg.move_player(&pid("wanderer"), Some("room-b"), "room-c");

        // Not lingering in the real origin (room-a) nor the stale one (room-b);
        // present exactly once, in room-c.
        assert!(reg.players_in_room("room-a").is_empty());
        assert!(reg.players_in_room("room-b").is_empty());
        assert_eq!(reg.players_in_room("room-c"), vec![pid("wanderer")]);
        assert_eq!(reg.occupied_rooms(), vec!["room-c".to_string()]);
    }

    #[test]
    fn register_reconciles_when_map_room_differs_from_connect_room() {
        // Mirrors connect() calling move_player(pid, current_tracked_room, new).
        let reg = ConnectionRegistry::new();
        let (tx1, _rx1) = open_channel();
        reg.register(pid("p"), tx1, Some("old".into()));
        assert_eq!(reg.players_in_room("old"), vec![pid("p")]);

        // Re-register into a new room; the old membership must be reconciled away.
        let (tx2, _rx2) = open_channel();
        reg.register(pid("p"), tx2, Some("new".into()));
        assert!(reg.players_in_room("old").is_empty());
        assert_eq!(reg.players_in_room("new"), vec![pid("p")]);
    }

    #[test]
    fn deregister_unknown_player_is_noop() {
        let reg = ConnectionRegistry::new();
        assert!(reg.deregister(&pid("ghost")).is_none());
    }
}
