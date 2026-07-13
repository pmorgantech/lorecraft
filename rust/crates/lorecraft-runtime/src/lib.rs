//! lorecraft-runtime — the world-actor skeleton.
//!
//! One actor owns one world. Commands arrive on a **bounded** input queue
//! (`std::sync::mpsc::sync_channel`), but determinism deliberately does **not**
//! depend on channel arrival order: the actor drains everything currently available
//! into a batch, sorts that batch by the `(logical_time, receive_sequence)` ordering
//! key ([`lorecraft_scheduler`]), then dispatches each command in that canonical
//! order to an injected policy.
//!
//! The actor is Tier 1 mechanism only — queue + ordering + dispatch. It holds no
//! feature-specific opinion about what any command *does*; that is the injected
//! [`CommandPolicy`]'s job (a Tier 2 concern, e.g. `lorecraft-feature-look`).

#![warn(missing_docs)]

use std::sync::mpsc::{sync_channel, Receiver, SyncSender, TrySendError};

use lorecraft_protocol::CommandEnvelope;
use lorecraft_scheduler::{sort_by_ordering_key, LogicalClock};

/// A sink for command envelopes injected into a world actor.
///
/// Wraps the bounded channel's [`SyncSender`]. `try_send` is non-blocking (returns
/// [`TrySendError::Full`] when the queue is at capacity); `send` blocks until space
/// is available. Cloneable so multiple producers can feed one actor.
#[derive(Clone)]
pub struct ActorInbox {
    sender: SyncSender<CommandEnvelope>,
}

impl ActorInbox {
    /// Attempt to enqueue a command without blocking.
    ///
    /// Returns [`TrySendError::Full`] if the bounded queue is at capacity, or
    /// [`TrySendError::Disconnected`] if the actor has been dropped.
    // The error carries the un-sent `CommandEnvelope` back to the caller — that is
    // std's channel contract, deliberately mirrored here rather than boxed.
    #[allow(clippy::result_large_err)]
    pub fn try_send(&self, envelope: CommandEnvelope) -> Result<(), TrySendError<CommandEnvelope>> {
        self.sender.try_send(envelope)
    }

    /// Enqueue a command, blocking until the bounded queue has room.
    // See `try_send`: the error returns the un-sent envelope, matching std.
    #[allow(clippy::result_large_err)]
    pub fn send(
        &self,
        envelope: CommandEnvelope,
    ) -> Result<(), std::sync::mpsc::SendError<CommandEnvelope>> {
        self.sender.send(envelope)
    }
}

/// The policy a world actor dispatches each ordered command to.
///
/// Kept abstract so the actor stays unopinionated: the actor decides *ordering*, the
/// policy decides *behavior*. A blanket impl lets any `FnMut(&CommandEnvelope, u64)`
/// serve as a policy, so tests and features can inject a closure.
pub trait CommandPolicy {
    /// Handle one command at its assigned `logical_time`, in canonical order.
    fn dispatch(&mut self, envelope: &CommandEnvelope, logical_time: u64);
}

impl<F> CommandPolicy for F
where
    F: FnMut(&CommandEnvelope, u64),
{
    fn dispatch(&mut self, envelope: &CommandEnvelope, logical_time: u64) {
        self(envelope, logical_time)
    }
}

/// A single-world actor: bounded input queue + deterministic ordering + dispatch.
pub struct WorldActor<P> {
    receiver: Receiver<CommandEnvelope>,
    clock: LogicalClock,
    policy: P,
}

/// Create a world actor with a bounded input queue of the given `capacity`.
///
/// Returns the [`ActorInbox`] producers push to, and the [`WorldActor`] that drains
/// and dispatches. `capacity` is the number of commands the queue buffers before a
/// blocking `send` waits (an operational tunable, static for this skeleton).
pub fn world_actor<P: CommandPolicy>(capacity: usize, policy: P) -> (ActorInbox, WorldActor<P>) {
    let (sender, receiver) = sync_channel(capacity);
    let actor = WorldActor {
        receiver,
        clock: LogicalClock::new(),
        policy,
    };
    (ActorInbox { sender }, actor)
}

impl<P: CommandPolicy> WorldActor<P> {
    /// Current logical time (advanced once per non-empty drain).
    pub fn logical_time(&self) -> u64 {
        self.clock.now()
    }

    /// Drain every command currently queued, sort by ordering key, and dispatch each
    /// in canonical order. Returns the number of commands dispatched.
    ///
    /// The whole drained batch shares one freshly-ticked `logical_time`, so ordering
    /// within a batch falls to `receive_sequence` — arrival order on the channel has
    /// no bearing on dispatch order. Returns `0` (without ticking) when the queue is
    /// empty.
    pub fn drain_and_dispatch(&mut self) -> usize {
        let mut batch: Vec<CommandEnvelope> = Vec::new();
        // `try_recv` errors on both Empty and Disconnected, ending the drain either
        // way — whatever was collected is processed first.
        while let Ok(envelope) = self.receiver.try_recv() {
            batch.push(envelope);
        }
        if batch.is_empty() {
            return 0;
        }

        let logical_time = self.clock.tick();
        sort_by_ordering_key(&mut batch, |_| logical_time);
        for envelope in &batch {
            self.policy.dispatch(envelope, logical_time);
        }
        batch.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::rc::Rc;

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
    fn bounded_queue_rejects_past_capacity() {
        // Nothing drains during this test, so the buffer fills and stays full.
        let (inbox, _actor) = world_actor(2, |_: &CommandEnvelope, _: u64| {});
        assert!(inbox.try_send(envelope("a", 0)).is_ok());
        assert!(inbox.try_send(envelope("b", 1)).is_ok());
        // Third send exceeds the capacity-2 buffer.
        match inbox.try_send(envelope("c", 2)) {
            Err(TrySendError::Full(_)) => {}
            other => panic!("expected Full, got {other:?}"),
        }
    }

    #[test]
    fn dispatch_order_is_by_ordering_key_not_arrival() {
        // Shared sink the fake policy records dispatch order into.
        let seen: Rc<RefCell<Vec<String>>> = Rc::new(RefCell::new(Vec::new()));
        let sink = Rc::clone(&seen);
        let policy = move |env: &CommandEnvelope, _lt: u64| {
            sink.borrow_mut().push(env.command_id.0.clone());
        };
        let (inbox, mut actor) = world_actor(8, policy);

        // Enqueue with deliberately out-of-order receive_sequence numbers.
        inbox.try_send(envelope("c", 30)).unwrap();
        inbox.try_send(envelope("a", 10)).unwrap();
        inbox.try_send(envelope("d", 40)).unwrap();
        inbox.try_send(envelope("b", 20)).unwrap();

        let dispatched = actor.drain_and_dispatch();
        assert_eq!(dispatched, 4);
        // Sorted by receive_sequence (batch shares one logical_time): a,b,c,d.
        assert_eq!(*seen.borrow(), vec!["a", "b", "c", "d"]);
    }

    #[test]
    fn empty_drain_does_not_advance_clock() {
        let (_inbox, mut actor) = world_actor(4, |_: &CommandEnvelope, _: u64| {});
        assert_eq!(actor.drain_and_dispatch(), 0);
        assert_eq!(actor.logical_time(), 0);
    }

    #[test]
    fn each_non_empty_drain_advances_logical_time_once() {
        let (inbox, mut actor) = world_actor(4, |_: &CommandEnvelope, _: u64| {});
        inbox.try_send(envelope("a", 0)).unwrap();
        inbox.try_send(envelope("b", 1)).unwrap();
        assert_eq!(actor.drain_and_dispatch(), 2);
        assert_eq!(actor.logical_time(), 1);

        inbox.try_send(envelope("c", 2)).unwrap();
        assert_eq!(actor.drain_and_dispatch(), 1);
        assert_eq!(actor.logical_time(), 2);
    }
}
