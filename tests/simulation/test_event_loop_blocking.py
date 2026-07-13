"""Characterization test of CURRENT synchronous event-loop blocking.

Rust-port Phase 0 evidence. The player command pipeline
(`main._handle_websocket_command`) runs `command_engine.handle_command(...)`
**synchronously** inside the single asyncio ingress task — no threadpool, no
`run_in_executor`. So a command handler that blocks the CPU/thread (a real
`time.sleep`, a slow synchronous DB call, a heavy computation) stalls the whole
event loop: every other connected player's in-flight command waits behind it
(head-of-line blocking).

This test *proves that blocking exists* by injecting a synchronous
`time.sleep(SLOW)` into one command handler and showing a concurrent, otherwise
instant command on a second connection is delayed by ~`SLOW`.

**This is a characterization of undesirable CURRENT behavior, not a
regression guard for desired behavior.** The Rust port moves command execution
off the ingress task (worker actors / a command queue), after which this exact
assertion should be *inverted* — the fast command should NOT be delayed. Do not
"fix" the blocking to make this pass differently; the point is to document the
starting condition the migration removes.

Injection strategy: monkeypatch `InventoryService.inventory` (the `inventory`
verb) to sleep synchronously. The verb handler resolves `service.inventory` at
call time, so patching the class method reaches the live in-process server. The
slow connection issues `inventory`; the fast connection issues `look` (a
different method, unpatched). `time.sleep` — not `asyncio.sleep` — is required:
only a real blocking call stalls the loop.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from lorecraft.features.inventory.service import InventoryService
from tests.simulation.conftest import SimulationServer
from tests.simulation.virtual_player import VirtualPlayer

pytestmark = pytest.mark.simulation

# How long the slow handler blocks the event loop.
SLOW = 0.5
# The fast command's measured latency must be at least this fraction of SLOW to
# prove it was stuck behind the blocking handler. Kept below 1.0 to absorb the
# small offset between when the slow handler starts and when the fast command is
# sent, plus scheduling jitter — while still being far above a non-blocked
# baseline (a bare `look` round-trips in single-digit ms).
BLOCKING_THRESHOLD = SLOW * 0.7
# How long after the slow command is dispatched the fast command is sent. Small
# relative to SLOW so the fast command lands while the loop is still blocked.
FAST_COMMAND_OFFSET = 0.05


def test_slow_synchronous_handler_blocks_a_concurrent_command(
    simulation_server: SimulationServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A synchronous `time.sleep` in one handler delays a concurrent command on
    another connection by ~SLOW — documenting current head-of-line blocking."""

    original_inventory = InventoryService.inventory

    def _slow_inventory(self: InventoryService, ctx: object) -> None:
        # Real, loop-blocking sleep — the whole point of the characterization.
        time.sleep(SLOW)
        original_inventory(self, ctx)  # type: ignore[arg-type]

    monkeypatch.setattr(InventoryService, "inventory", _slow_inventory)

    asyncio.run(_run_blocking_probe(simulation_server))


async def _run_blocking_probe(server: SimulationServer) -> None:
    slow_id = server.create_player("blocking_slow")
    fast_id = server.create_player("blocking_fast")

    slow_player = await VirtualPlayer.connect(server.ws_url, slow_id, "blocking_slow")
    fast_player = await VirtualPlayer.connect(server.ws_url, fast_id, "blocking_fast")
    try:
        # Fire the slow command; it starts blocking the shared event loop.
        slow_task = asyncio.create_task(slow_player.send_command("inventory"))
        # Send the fast command shortly after, while the loop is still blocked,
        # and measure only its round-trip.
        await asyncio.sleep(FAST_COMMAND_OFFSET)
        fast_start = time.perf_counter()
        await fast_player.send_command("look")
        fast_latency = time.perf_counter() - fast_start

        await slow_task
    finally:
        await asyncio.gather(
            slow_player.close(), fast_player.close(), return_exceptions=True
        )

    assert fast_latency >= BLOCKING_THRESHOLD, (
        f"expected the concurrent `look` to be delayed >= {BLOCKING_THRESHOLD:.3f}s "
        f"by the blocking `inventory` handler (head-of-line blocking), but it "
        f"returned in {fast_latency:.3f}s. If this now fails because commands run "
        "off the ingress task, the Rust-port migration has landed — invert this "
        "assertion (see the module docstring)."
    )
