//! `writer.rs` — the shared per-connection outbound writer task (Phase 3c).
//!
//! Both the player (`/ws`) and admin (`/admin/ws`) handlers own the WebSocket
//! **sink** on a dedicated task that drains the connection's bounded outbound queue
//! (design decision 9/10). Phase 3c gives that drain two new responsibilities on
//! top of "serialize each opaque payload as a text frame":
//!
//! 1. **Coalescing (item 4).** The writer folds the frames it pulls from the mpsc
//!    through a keep-latest [`CoalescingQueue`]: two buffered frames sharing a
//!    non-`None` `coalesce_key` (idempotent panel/`state_change` refreshes the
//!    Python policy owner stamped) collapse to the latest; keyless frames
//!    (`feed_append`) never coalesce and are written in strict FIFO order, never
//!    dropped. Coalescing only ever folds frames that are *already queued*
//!    (drained non-blockingly with `try_recv`), and the writer stops draining once
//!    the coalescer is full — so it can never silently drop a keyless frame, and,
//!    critically, it **never empties the mpsc while the sink is stalled**. A stalled
//!    sink parks the writer in the write `select!` below, so the mpsc fills and
//!    `dispatch`'s overflow tracker still trips: coalescing does not defeat the
//!    slow-client disconnect (item 3).
//!
//! 2. **Slow-client close (item 3).** The writer `select!`s a
//!    [`watch::Receiver<bool>`] close signal (see [`crate::disconnect`]) against
//!    every blocking step (both awaiting the next frame and awaiting the sink). When
//!    the signal flips, the writer closes the WebSocket with code **1013**
//!    (`BackpressureDisconnect::SlowConsumer::ws_close_code`, "Try Again Later") and
//!    exits — bounded by [`SLOW_CLIENT_CLOSE_GRACE`] so a genuinely stalled socket
//!    whose close frame can never flush is still torn down.
//!
//! The writer exits cleanly (no close frame) when its queue is dropped — the normal
//! teardown path, where the owning handler closes the socket by dropping the stream
//! half.

use std::time::Duration;

use axum::extract::ws::{CloseFrame, Message, Utf8Bytes, WebSocket};
use futures_util::stream::SplitSink;
use futures_util::SinkExt;
use lorecraft_events::{BackpressureDisconnect, CoalescingQueue, OutboundFrame};
use tokio::sync::{mpsc, watch};
use tokio::time::timeout;

/// How long the writer will wait for a slow-client `Close(1013)` frame to flush
/// before giving up and dropping the sink. A stalled consumer's socket may never
/// accept the close (its buffers are full); this bounds how long the writer task
/// lingers on such a socket while still giving a client that resumes reading time to
/// observe the intended 1013 close code rather than a bare transport drop (1006).
const SLOW_CLIENT_CLOSE_GRACE: Duration = Duration::from_secs(5);

/// The outcome of the writer's inner "produce next frame" step.
enum Step {
    /// A frame is ready to buffer (payload + optional coalesce key).
    Write(OutboundFrame),
    /// The close signal fired — tear the socket down with 1013.
    Close,
    /// The queue was dropped — normal teardown, exit without a close frame.
    Done,
}

/// Drive one connection's outbound writer to completion (see the module docs).
///
/// `coalesce_capacity` bounds the writer-side [`CoalescingQueue`]; the handlers pass
/// the connection's configured outbound-queue depth so the coalescing buffer and the
/// transport queue share one depth budget.
pub(crate) async fn writer_task(
    mut sink: SplitSink<WebSocket, Message>,
    mut queue: mpsc::Receiver<OutboundFrame>,
    mut close_rx: watch::Receiver<bool>,
    coalesce_capacity: usize,
) {
    let mut coalescer = CoalescingQueue::new(coalesce_capacity);
    loop {
        // Refill from the queue if we have nothing buffered, blocking for the next
        // frame or a close signal. Then opportunistically fold any *already-ready*
        // frames without blocking (this is where same-key coalescing happens).
        if coalescer.is_empty() {
            match next_frame(&mut queue, &mut close_rx).await {
                Step::Write(frame) => {
                    // `coalescer` was empty; seed it (preserving the key) and fall
                    // through to the non-blocking drain that folds in ready frames.
                    coalescer.enqueue(frame.payload, frame.coalesce_key);
                }
                Step::Close => {
                    close_slow(&mut sink).await;
                    return;
                }
                Step::Done => return,
            }
        }
        drain_ready(&mut queue, &mut coalescer);

        // Write everything buffered, honoring the close signal between/within writes
        // so a stalled sink can always be interrupted.
        while let Some(payload) = coalescer.dequeue() {
            match write_one(&mut sink, &mut close_rx, payload).await {
                WriteOutcome::Continue => {}
                WriteOutcome::Close => {
                    close_slow(&mut sink).await;
                    return;
                }
                WriteOutcome::SinkGone => return,
            }
        }
    }
}

/// Block for the next queued frame or a close signal.
async fn next_frame(
    queue: &mut mpsc::Receiver<OutboundFrame>,
    close_rx: &mut watch::Receiver<bool>,
) -> Step {
    tokio::select! {
        biased;
        res = close_rx.changed() => {
            if res.is_ok() && *close_rx.borrow_and_update() {
                Step::Close
            } else {
                // Sender dropped (Err) or a spurious unset — treat as normal exit.
                Step::Done
            }
        }
        maybe = queue.recv() => match maybe {
            Some(frame) => Step::Write(frame),
            None => Step::Done,
        }
    }
}

/// Non-blockingly fold every already-ready frame into the coalescer, stopping once
/// it is full so a keyless frame is left in the mpsc (backpressure) rather than
/// dropped. Same-key frames replace in place and do not grow the buffer.
fn drain_ready(queue: &mut mpsc::Receiver<OutboundFrame>, coalescer: &mut CoalescingQueue) {
    loop {
        if coalescer.len() >= coalescer.capacity() {
            break;
        }
        match queue.try_recv() {
            Ok(frame) => {
                coalescer.enqueue(frame.payload, frame.coalesce_key);
            }
            Err(_) => break,
        }
    }
}

/// The outcome of attempting to write one payload.
enum WriteOutcome {
    /// Written; keep going.
    Continue,
    /// Close signal fired mid-write — tear down with 1013.
    Close,
    /// The sink errored (client unreadable) — exit without a crafted close.
    SinkGone,
}

/// Write one payload, cancellable by the close signal.
async fn write_one(
    sink: &mut SplitSink<WebSocket, Message>,
    close_rx: &mut watch::Receiver<bool>,
    payload: serde_json::Value,
) -> WriteOutcome {
    let text = payload.to_string();
    tokio::select! {
        biased;
        res = close_rx.changed() => {
            if res.is_ok() && *close_rx.borrow_and_update() {
                WriteOutcome::Close
            } else {
                WriteOutcome::SinkGone
            }
        }
        send = sink.send(Message::Text(Utf8Bytes::from(text))) => {
            if send.is_err() {
                tracing::debug!("outbound write failed; writer exiting");
                WriteOutcome::SinkGone
            } else {
                WriteOutcome::Continue
            }
        }
    }
}

/// Best-effort close the WebSocket with the slow-consumer code (1013), bounded by
/// [`SLOW_CLIENT_CLOSE_GRACE`] so a socket that will never accept the frame cannot
/// wedge the writer task.
async fn close_slow(sink: &mut SplitSink<WebSocket, Message>) {
    let frame = CloseFrame {
        code: BackpressureDisconnect::SlowConsumer.ws_close_code(),
        reason: Utf8Bytes::from(BackpressureDisconnect::SlowConsumer.as_str().to_owned()),
    };
    match timeout(
        SLOW_CLIENT_CLOSE_GRACE,
        sink.send(Message::Close(Some(frame))),
    )
    .await
    {
        Ok(Ok(())) => {}
        Ok(Err(err)) => tracing::debug!(error = %err, "slow-client 1013 close not delivered"),
        Err(_) => tracing::debug!("slow-client 1013 close timed out; dropping sink (1006)"),
    }
}
