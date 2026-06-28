"""Admin push broadcaster: fans out events to connected admin WebSocket queues."""

from __future__ import annotations

import asyncio

from lorecraft.types import JsonObject


class AdminBroadcaster:
    """Thread-safe (single-event-loop) fan-out to all admin WS connections."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[JsonObject]] = set()

    def add(self, q: asyncio.Queue[JsonObject]) -> None:
        self._queues.add(q)

    def remove(self, q: asyncio.Queue[JsonObject]) -> None:
        self._queues.discard(q)

    def push(self, message: JsonObject) -> None:
        """Enqueue message for every connected admin client. Safe to call from sync code."""
        for q in self._queues:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass

    @property
    def connection_count(self) -> int:
        return len(self._queues)
