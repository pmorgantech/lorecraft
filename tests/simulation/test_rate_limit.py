"""Phase 3c: the per-player command rate limit (design decision 10), end to end
through the Rust gateway.

The rate limit is a **new, Rust-side** protection: the gateway meters each
player's command intake with a generous token bucket (burst 20, ~5/s sustained by
default — see `lorecraft_events::RateLimitConfig`). A client that floods commands
past the burst gets each excess command rejected **in band** with a
``{"type":"error","code":"rate_limited"}`` frame (the connection stays open — it
is a throttle, not a disconnect), while a client sending at any human-plausible
cadence never approaches the limit.

Both facts are asserted against the **real** Rust front door (`rust_gateway_server`
forces the gateway on regardless of `LORECRAFT_THROUGH_RUST`, since the mechanism
lives only in Rust): a flooder on one connection is throttled while a co-located
normal-cadence client on a second connection is completely unaffected.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
import websockets

from tests.simulation.conftest import SimulationServer
from tests.simulation.virtual_player import VirtualPlayer

pytestmark = pytest.mark.simulation

# Default token-bucket burst is 20; sending comfortably more than that in one
# rapid volley must produce at least one throttle once the burst is spent.
_FLOOD_COMMANDS = 40


async def _drain(ws: Any, *, window: float) -> list[dict[str, Any]]:
    """Collect every JSON frame that arrives within a fixed `window`-second budget.

    A *total* wall-clock budget, not an idle timeout: the live world clock pushes
    periodic global ``time_update`` broadcasts, so the socket is never quiet for
    long — an "until N seconds of silence" drain would never return. Those
    incidental broadcasts are harmless here (the caller filters for
    ``rate_limited`` / ``command_result``).
    """
    frames: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + window
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            break
        frames.append(json.loads(raw))
    return frames


def _is_rate_limited(frame: dict[str, Any]) -> bool:
    return frame.get("type") == "error" and frame.get("code") == "rate_limited"


async def _run(server: SimulationServer) -> None:
    # A co-located normal-cadence client whose experience must be untouched.
    normal_id, normal_ticket = server.prepare_login("polite_player")
    normal = await VirtualPlayer.connect(
        server.ws_url, normal_id, "polite_player", ticket=normal_ticket
    )
    # The flooder.
    flood_id, flood_ticket = server.prepare_login("flooder")
    flooder = await VirtualPlayer.connect(
        server.ws_url, flood_id, "flooder", ticket=flood_ticket
    )

    try:
        # Flood: fire well past the burst as fast as the socket accepts, without
        # waiting for replies, so the excess overruns the token bucket.
        for _ in range(_FLOOD_COMMANDS):
            await flooder._ws.send("look")
        flood_frames = await _drain(flooder._ws, window=2.0)

        throttled = [f for f in flood_frames if _is_rate_limited(f)]
        admitted = [f for f in flood_frames if f.get("type") == "command_result"]
        assert throttled, (
            "flooding past the burst must yield at least one rate_limited frame; "
            f"got types {sorted({str(f.get('type')) for f in flood_frames})}"
        )
        # It is a throttle of the *excess*, not a blanket rejection: the burst was
        # admitted and executed, and the connection stayed open (no close frame).
        assert admitted, "expected the burst of commands to be admitted + executed"
        assert flooder._ws.close_code is None, "rate limit must not close the socket"

        # The co-located normal client, sending at ~4 cmd/s (under the 5/s refill),
        # is never throttled and every command executes.
        for _ in range(6):
            reply = await asyncio.wait_for(normal.send_command("look"), timeout=5.0)
            assert reply.get("type") == "command_result"
            await asyncio.sleep(0.25)
        # Nothing rate-limited ever landed on the polite client's socket.
        assert not any(_is_rate_limited(m) for m in normal.messages), (
            "a normal-cadence client must never be rate limited"
        )
    finally:
        await flooder.close()
        await normal.close()


def test_flood_is_rate_limited_while_normal_cadence_is_unaffected(
    rust_gateway_server: SimulationServer,
) -> None:
    asyncio.run(_run(rust_gateway_server))
