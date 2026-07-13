"""Admin push broadcaster: fans out events to connected admin WebSocket queues."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from lorecraft.types import JsonObject


class AdminBroadcaster:
    """Thread-safe (single-event-loop) fan-out to all admin WS connections.

    An optional *gateway sink* (Rust-port Phase 3c) lets a caller ALSO relay every
    pushed event elsewhere. In gateway mode admin consoles connect to Rust rather
    than this process's ``/admin/ws`` queues, so the composition layer registers a
    sink (``AdminGatewaySink``) that forwards each event to the Rust gateway. The
    sink is purely additive: when it is unset (the default, and the flag-off
    rollback path) ``push`` behaves exactly as before.
    """

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[JsonObject]] = set()
        self._gateway_sink: Callable[[JsonObject], None] | None = None

    def add(self, q: asyncio.Queue[JsonObject]) -> None:
        self._queues.add(q)

    def remove(self, q: asyncio.Queue[JsonObject]) -> None:
        self._queues.discard(q)

    def set_gateway_sink(self, sink: Callable[[JsonObject], None] | None) -> None:
        """Register (or clear) a sink that also receives every pushed event.

        The composition layer wires this in gateway mode so admin events reach the
        Rust-owned admin consoles; the broadcaster itself stays ignorant of the
        gateway/protocol types (the sink is a plain callable).
        """
        self._gateway_sink = sink

    def push(self, message: JsonObject) -> None:
        """Enqueue message for every connected admin client. Safe to call from sync code."""
        for q in self._queues:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass
        if self._gateway_sink is not None:
            self._gateway_sink(message)

    @property
    def connection_count(self) -> int:
        return len(self._queues)
