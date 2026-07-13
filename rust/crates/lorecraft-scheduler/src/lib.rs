//! lorecraft-scheduler — deterministic ordering key + injected logical clock.
//!
//! Actor-local determinism does not depend on channel arrival order. Commands are
//! ordered by an explicit `(logical_time, receive_sequence)` key so a drained batch
//! always dispatches in the same canonical order regardless of how it was enqueued.
//!
//! This crate is Tier 1 mechanism: it knows *how* to order and *how* to advance a
//! logical clock, but holds no feature opinion about what any command does.

#![warn(missing_docs)]

use lorecraft_protocol::CommandEnvelope;

/// The deterministic ordering key for a command: `(logical_time, receive_sequence)`.
///
/// `Ord` is the derived lexicographic tuple order — `logical_time` dominates, with
/// `receive_sequence` breaking ties. This is the single source of truth for
/// actor-local dispatch order.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct OrderingKey {
    /// Logical clock value assigned to the command.
    pub logical_time: u64,
    /// Monotonic admission/client sequence number.
    pub receive_sequence: u64,
}

impl OrderingKey {
    /// Construct an ordering key from its two components.
    pub fn new(logical_time: u64, receive_sequence: u64) -> Self {
        Self {
            logical_time,
            receive_sequence,
        }
    }
}

/// Extract the [`OrderingKey`] for a command envelope.
///
/// The envelope carries `receive_sequence` directly; the `logical_time` is supplied
/// by the caller because it is assigned by the actor's logical clock at admission,
/// not stored on the wire envelope.
pub fn ordering_key(envelope: &CommandEnvelope, logical_time: u64) -> OrderingKey {
    OrderingKey::new(logical_time, envelope.receive_sequence)
}

/// Sort envelopes in place by their ordering key.
///
/// `logical_time` is looked up per-envelope via `logical_time_of` (the actor knows
/// each command's admission time). Uses a stable sort so equal keys keep their
/// relative input order — though keys are expected unique per actor.
pub fn sort_by_ordering_key<F>(envelopes: &mut [CommandEnvelope], logical_time_of: F)
where
    F: Fn(&CommandEnvelope) -> u64,
{
    envelopes.sort_by_key(|env| ordering_key(env, logical_time_of(env)));
}

/// A monotonically-advancing logical clock.
///
/// Injected rather than derived from wall-clock time — determinism requires that the
/// clock never reads `SystemTime::now()`. Callers advance it explicitly; `tick`
/// returns the freshly-advanced value.
#[derive(Debug, Clone, Default)]
pub struct LogicalClock {
    current: u64,
}

impl LogicalClock {
    /// Create a clock starting at logical time zero.
    pub fn new() -> Self {
        Self::default()
    }

    /// Create a clock starting at an explicit logical time.
    pub fn starting_at(start: u64) -> Self {
        Self { current: start }
    }

    /// Return the current logical time without advancing.
    pub fn now(&self) -> u64 {
        self.current
    }

    /// Advance the clock by one and return the new value.
    ///
    /// Saturates at `u64::MAX` rather than wrapping — a wrap would break the
    /// monotonicity the ordering key relies on.
    pub fn tick(&mut self) -> u64 {
        self.current = self.current.saturating_add(1);
        self.current
    }

    /// Advance the clock so it is at least `at_least`, then return the new value.
    ///
    /// Used when merging an externally-observed logical time (e.g. from a peer)
    /// without ever moving the clock backward.
    pub fn observe(&mut self, at_least: u64) -> u64 {
        self.current = self.current.max(at_least);
        self.current
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use lorecraft_protocol::{
        ActorId, CommandEnvelope, CommandId, PlayerId, SessionId, WorldId, PROTOCOL_VERSION,
    };

    fn envelope(command_id: &str, receive_sequence: u64) -> CommandEnvelope {
        CommandEnvelope {
            protocol_version: PROTOCOL_VERSION,
            world_id: WorldId("world-1".into()),
            actor_id: ActorId("actor-1".into()),
            player_id: PlayerId("player-1".into()),
            session_id: SessionId("session-1".into()),
            command_id: CommandId(command_id.into()),
            receive_sequence,
            deadline_ms: 5_000,
            raw: "look".into(),
        }
    }

    #[test]
    fn ordering_key_is_lexicographic() {
        // logical_time dominates receive_sequence.
        assert!(OrderingKey::new(1, 99) < OrderingKey::new(2, 0));
        // ties broken by receive_sequence.
        assert!(OrderingKey::new(5, 1) < OrderingKey::new(5, 2));
        assert_eq!(OrderingKey::new(3, 7), OrderingKey::new(3, 7));
    }

    #[test]
    fn sort_orders_by_logical_time_then_sequence_regardless_of_insertion() {
        // Insertion order is deliberately scrambled; keyed by command id.
        let mut envelopes = vec![
            envelope("c", 2), // lt 5, seq 2
            envelope("a", 9), // lt 1, seq 9
            envelope("d", 1), // lt 5, seq 1
            envelope("b", 0), // lt 1, seq 0
        ];
        let logical_time_of = |env: &CommandEnvelope| match env.command_id.0.as_str() {
            "a" | "b" => 1,
            _ => 5,
        };
        sort_by_ordering_key(&mut envelopes, logical_time_of);
        let order: Vec<&str> = envelopes.iter().map(|e| e.command_id.0.as_str()).collect();
        // Expected: (1,0)=b, (1,9)=a, (5,1)=d, (5,2)=c
        assert_eq!(order, vec!["b", "a", "d", "c"]);
    }

    #[test]
    fn sort_is_stable_across_different_insertion_orders() {
        let logical_time_of = |_: &CommandEnvelope| 0_u64;
        let mut forward = vec![envelope("x", 3), envelope("y", 1), envelope("z", 2)];
        let mut reverse = vec![envelope("z", 2), envelope("y", 1), envelope("x", 3)];
        sort_by_ordering_key(&mut forward, logical_time_of);
        sort_by_ordering_key(&mut reverse, logical_time_of);
        let ids = |v: &[CommandEnvelope]| -> Vec<String> {
            v.iter().map(|e| e.command_id.0.clone()).collect()
        };
        assert_eq!(ids(&forward), ids(&reverse));
        assert_eq!(ids(&forward), vec!["y", "z", "x"]);
    }

    #[test]
    fn logical_clock_advances_monotonically() {
        let mut clock = LogicalClock::new();
        assert_eq!(clock.now(), 0);
        assert_eq!(clock.tick(), 1);
        assert_eq!(clock.tick(), 2);
        assert_eq!(clock.now(), 2);
    }

    #[test]
    fn logical_clock_observe_never_moves_backward() {
        let mut clock = LogicalClock::starting_at(10);
        assert_eq!(clock.observe(5), 10); // no backward move
        assert_eq!(clock.observe(15), 15); // jumps forward
        assert_eq!(clock.tick(), 16);
    }

    #[test]
    fn logical_clock_saturates_instead_of_wrapping() {
        let mut clock = LogicalClock::starting_at(u64::MAX);
        assert_eq!(clock.tick(), u64::MAX);
    }
}
