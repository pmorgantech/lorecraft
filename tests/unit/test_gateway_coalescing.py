"""Coalescing policy + admin-broadcast gateway sink (Rust-port Phase 3c).

Covers the Tier 2 coalescing *policy* (`coalesce_key_for`) that decides which
`DeliveryDirective`s Rust's outbound-queue mechanism may keep-latest-collapse, the
stamping of that key at every directive-building site (command effects via
`DirectiveConnectionManager`, autonomous broadcasts via `GatewayPushManager`), and
the `AdminGatewaySink` that relays admin broadcasts to Rust as `Deliver(Admin)`
frames only when gateway mode is on.
"""

from __future__ import annotations

import asyncio
from typing import cast

import pytest

from lorecraft.gateway.adapter import (
    AdminGatewaySink,
    GatewayAdapter,
    GatewayPushManager,
)
from lorecraft.gateway.coalescing import coalesce_key_for
from lorecraft.gateway.connection_manager import DirectiveConnectionManager
from lorecraft.protocol.gateway import AdminTarget, DeliveryDirective
from lorecraft.types import JsonObject, JsonValue
from lorecraft.webui.admin.broadcaster import AdminBroadcaster


class _RecordingAdapter:
    """Stands in for `GatewayAdapter`, recording every `push_deliver` directive."""

    def __init__(self) -> None:
        self.pushed: list[DeliveryDirective] = []

    async def push_deliver(self, directive: DeliveryDirective) -> None:
        self.pushed.append(directive)


# --- coalesce_key_for policy -----------------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        # state_change / panel refresh -> keyed on the affected-panel signature.
        (
            {"type": "state_change", "affected_panels": ["players-online"]},
            "state_change:players-online",
        ),
        # Panel set is order-insensitive: same key regardless of list order.
        ({"type": "state_change", "affected_panels": ["b", "a"]}, "state_change:a,b"),
        # Different panel sets must NOT share a key (no cross-panel clobber).
        (
            {"type": "state_change", "affected_panels": ["inventory"]},
            "state_change:inventory",
        ),
        ({"type": "state_change"}, "state_change:"),
        # content_changed is the admin panel-refresh nudge -> keyed per resource.
        ({"type": "content_changed", "resource": "issues"}, "content_changed:issues"),
        ({"type": "content_changed", "resource": "news"}, "content_changed:news"),
        # Discrete events that must all arrive -> never coalesced.
        ({"type": "feed_append", "content": "hi"}, None),
        ({"type": "chat", "content": "yo"}, None),
        ({"type": "player_joined", "player_id": "p1"}, None),
        ({"type": "player_left", "player_id": "p1"}, None),
        ({"type": "connected", "player_id": "p1"}, None),
        ({"type": "audit_appended", "summary": "x"}, None),
        ({"type": "time_update", "hour": 3}, None),
        # Non-dict payloads are never coalesced.
        ("not-a-dict", None),
        (None, None),
    ],
)
def test_coalesce_key_for(payload: JsonValue, expected: str | None) -> None:
    assert coalesce_key_for(payload) == expected


def test_state_change_panel_order_is_normalized() -> None:
    """Two refreshes of the same panels collapse regardless of list order."""
    a = coalesce_key_for({"type": "state_change", "affected_panels": ["a", "b"]})
    b = coalesce_key_for({"type": "state_change", "affected_panels": ["b", "a"]})
    assert a == b


# --- DirectiveConnectionManager (command effects) stamps the key -----------


def test_command_manager_stamps_state_change_key() -> None:
    mgr = DirectiveConnectionManager()
    asyncio.run(
        mgr.broadcast_to_room(
            "room-1", {"type": "state_change", "affected_panels": ["players-online"]}
        )
    )
    (directive,) = mgr.drain()
    assert directive.coalesce_key == "state_change:players-online"


def test_command_manager_leaves_feed_append_keyless() -> None:
    mgr = DirectiveConnectionManager()
    asyncio.run(
        mgr.broadcast_to_room("room-1", {"type": "feed_append", "content": "hi"})
    )
    (directive,) = mgr.drain()
    assert directive.coalesce_key is None


# --- GatewayPushManager (autonomous broadcasts) stamps the key -------------


def test_push_manager_stamps_state_change_key() -> None:
    fake = _RecordingAdapter()
    pm = GatewayPushManager()
    pm.bind(cast(GatewayAdapter, fake))
    asyncio.run(
        pm.broadcast_global({"type": "state_change", "affected_panels": ["map"]})
    )
    assert fake.pushed[0].coalesce_key == "state_change:map"


def test_push_manager_leaves_time_update_keyless() -> None:
    fake = _RecordingAdapter()
    pm = GatewayPushManager()
    pm.bind(cast(GatewayAdapter, fake))
    asyncio.run(pm.broadcast_global({"type": "time_update", "hour": 5}))
    assert fake.pushed[0].coalesce_key is None


# --- AdminGatewaySink ------------------------------------------------------


def test_admin_sink_directive_for_targets_admin_with_key() -> None:
    sink = AdminGatewaySink()
    event: JsonObject = {"type": "content_changed", "resource": "issues"}
    directive = sink.directive_for(event)
    assert isinstance(directive.target, AdminTarget)
    assert directive.exclude is None
    assert directive.payload == event
    assert directive.coalesce_key == "content_changed:issues"


def test_admin_sink_unbound_is_noop() -> None:
    """Before `bind` (or with no adapter) the sink drops the event harmlessly."""
    sink = AdminGatewaySink()

    async def _run() -> None:
        sink({"type": "content_changed", "resource": "issues"})

    asyncio.run(_run())  # must not raise


def test_broadcaster_forwards_to_gateway_when_sink_set() -> None:
    """Gateway mode: an admin push reaches the adapter as a Deliver(Admin) directive."""
    fake = _RecordingAdapter()
    sink = AdminGatewaySink()
    sink.bind(cast(GatewayAdapter, fake))
    broadcaster = AdminBroadcaster()
    broadcaster.set_gateway_sink(sink)

    async def _run() -> None:
        broadcaster.push({"type": "player_moved", "player_id": "p1"})
        broadcaster.push(
            {"type": "state_change", "affected_panels": ["players-online"]}
        )
        # Let the scheduled push_deliver tasks run to completion.
        for _ in range(4):
            await asyncio.sleep(0)

    asyncio.run(_run())

    assert len(fake.pushed) == 2
    assert all(isinstance(d.target, AdminTarget) for d in fake.pushed)
    assert fake.pushed[0].payload == {"type": "player_moved", "player_id": "p1"}
    assert fake.pushed[0].coalesce_key is None  # discrete event
    assert fake.pushed[1].coalesce_key == "state_change:players-online"


def test_broadcaster_flag_off_uses_local_queue_not_gateway() -> None:
    """Flag off (no sink): the legacy per-connection queue path is untouched."""
    broadcaster = AdminBroadcaster()
    fake = _RecordingAdapter()  # deliberately never registered as a sink

    async def _run() -> JsonObject:
        q: asyncio.Queue[JsonObject] = asyncio.Queue()
        broadcaster.add(q)
        broadcaster.push({"type": "content_changed", "resource": "issues"})
        for _ in range(4):
            await asyncio.sleep(0)
        return await q.get()

    delivered = asyncio.run(_run())
    assert delivered == {"type": "content_changed", "resource": "issues"}
    assert fake.pushed == []  # nothing relayed to the gateway
