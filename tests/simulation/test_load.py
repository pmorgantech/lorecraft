"""Multi-player load test (Sprint 37.3).

N concurrent `VirtualPlayer`s issue a fixed command script over real
WebSockets against a live server; the test reports p50/p95/p99/max command
latency. The server is single-process/single-threaded (architecture.md §1),
so the players' commands queue on one event loop and are processed one at a
time — this measures how command latency degrades as concurrent load rises,
which is the evidence the Sprint 38 concurrency-decision gate needs.

Marked `simulation`, so it's excluded from the default suite. Run it to
capture the before/after picture around a scaling change (e.g. Sprint 37.1
scheduler batching):

    make test-simulation                       # default 10 players
    LORECRAFT_LOAD_TEST_PLAYERS=25 \\
        .venv/bin/python -m pytest -s tests/simulation/test_load.py -m simulation
    LORECRAFT_LOAD_TEST_JSON=/tmp/before.json \\
        .venv/bin/python -m pytest -s tests/simulation/test_load.py -m simulation

`-s` surfaces the printed summary; `LORECRAFT_LOAD_TEST_JSON` also writes it as
machine-readable JSON for a scripted before/after diff. See docs/roadmap.md
Sprint 37.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

import pytest

from tests.simulation.conftest import SimulationServer
from tests.simulation.virtual_player import VirtualPlayer

pytestmark = pytest.mark.simulation

# Read-heavy loop each player repeats. `look`/`inventory`/`who` are always
# valid and don't mutate shared state; the `go east`/`go west` pair exercises
# movement + room-broadcast fan-out. Even a move with no exit still returns a
# `command_result`, so latency is measured for every command regardless.
_SCRIPT = ["look", "inventory", "who", "go east", "look", "go west"]

_DEFAULT_PLAYERS = 10
_LATENCY_CEILING_MS = 2000.0  # generous — trips only on a hang/gross regression


def _percentile(sorted_ms: list[float], fraction: float) -> float:
    """Nearest-rank percentile; `sorted_ms` must be sorted ascending."""
    if not sorted_ms:
        return 0.0
    index = min(len(sorted_ms) - 1, int(len(sorted_ms) * fraction))
    return round(sorted_ms[index], 3)


def test_concurrent_players_command_latency(
    simulation_server: SimulationServer,
) -> None:
    player_count = int(os.getenv("LORECRAFT_LOAD_TEST_PLAYERS", str(_DEFAULT_PLAYERS)))
    # Character creation is setup, not part of the measured load — do it
    # synchronously up front so the async phase is purely connect + drive.
    credentials = [
        (simulation_server.create_player(name), name)
        for name in (f"load_{i}_{uuid.uuid4().hex[:6]}" for i in range(player_count))
    ]
    report = asyncio.run(_run_load(simulation_server, credentials))

    print(
        f"\nLoad test — {report['players']} concurrent players × "
        f"{report['commands_per_player']} commands ({report['total_commands']} total)\n"
        f"  p50={report['p50_ms']} ms  p95={report['p95_ms']} ms  "
        f"p99={report['p99_ms']} ms  max={report['max_ms']} ms"
    )
    out_path = os.getenv("LORECRAFT_LOAD_TEST_JSON")
    if out_path:
        Path(out_path).write_text(json.dumps(report, indent=2))

    assert report["total_commands"] == player_count * len(_SCRIPT)
    # Sanity gate: catches a hung/broken server or a gross regression without
    # being so tight it flakes on a loaded CI box.
    assert report["p99_ms"] < _LATENCY_CEILING_MS


async def _run_load(
    server: SimulationServer, credentials: list[tuple[str, str]]
) -> dict[str, float | int]:
    # Connect sequentially (setup, not measured): concurrent connects to the
    # same starting room race each socket's `connected` handshake against the
    # `player_joined` broadcasts from other joins. The measured load is the
    # concurrent command drive below.
    players: list[VirtualPlayer] = []
    for player_id, username in credentials:
        players.append(await VirtualPlayer.connect(server.ws_url, player_id, username))
    try:
        per_player = await asyncio.gather(*(_drive(player) for player in players))
    finally:
        await asyncio.gather(
            *(player.close() for player in players), return_exceptions=True
        )

    latencies_ms = sorted(
        ms for player_latencies in per_player for ms in player_latencies
    )
    return {
        "players": len(credentials),
        "commands_per_player": len(_SCRIPT),
        "total_commands": len(latencies_ms),
        "p50_ms": _percentile(latencies_ms, 0.50),
        "p95_ms": _percentile(latencies_ms, 0.95),
        "p99_ms": _percentile(latencies_ms, 0.99),
        "max_ms": round(latencies_ms[-1], 3) if latencies_ms else 0.0,
    }


async def _drive(player: VirtualPlayer) -> list[float]:
    """Run the script once, returning per-command round-trip latency in ms."""
    latencies: list[float] = []
    for command in _SCRIPT:
        start = time.perf_counter()
        await player.send_command(command)
        latencies.append((time.perf_counter() - start) * 1000.0)
    return latencies
