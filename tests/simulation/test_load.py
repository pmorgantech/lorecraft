"""Multi-player load test (Sprint 37.3; scenario-driven since Sprint 43.2).

N concurrent `VirtualPlayer`s replay a recorded scenario over real WebSockets
against a live server; the test reports p50/p95/p99/max command latency. The
server is single-process/single-threaded (architecture.md §1), so the
players' commands queue on one event loop and are processed one at a time —
this measures how command latency degrades as concurrent load rises.

The traffic is a Sprint 43 scenario file rather than a hard-coded script:
`scenarios/load_default.json` ships the original read-heavy loop, and
`LORECRAFT_LOAD_TEST_SCENARIO` points the same harness at any recorded
session (e.g. one captured from real play with
`python -m lorecraft.tools.session_replay record`).

Marked `simulation`, so it's excluded from the default suite. Run it to
capture the before/after picture around a scaling change:

    make test-simulation                       # default 10 players
    LORECRAFT_LOAD_TEST_PLAYERS=25 \\
        .venv/bin/python -m pytest -s tests/simulation/test_load.py -m simulation
    LORECRAFT_LOAD_TEST_SCENARIO=/tmp/real_session.json \\
        .venv/bin/python -m pytest -s tests/simulation/test_load.py -m simulation
    LORECRAFT_LOAD_TEST_JSON=/tmp/before.json \\
        .venv/bin/python -m pytest -s tests/simulation/test_load.py -m simulation

`-s` surfaces the printed summary; `LORECRAFT_LOAD_TEST_JSON` also writes it as
machine-readable JSON for a scripted before/after diff. See docs/roadmap.md
Sprints 37 and 43.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from lorecraft.tools.session_replay import load_scenario
from tests.simulation.conftest import SimulationServer
from tests.simulation.replay import fan_out_scenario

pytestmark = pytest.mark.simulation

_DEFAULT_SCENARIO = Path(__file__).parent / "scenarios" / "load_default.json"
_DEFAULT_PLAYERS = 10
_LATENCY_CEILING_MS = 2000.0  # generous — trips only on a hang/gross regression


def test_concurrent_players_command_latency(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    scenario_path = Path(os.getenv("LORECRAFT_LOAD_TEST_SCENARIO") or _DEFAULT_SCENARIO)
    scenario = load_scenario(scenario_path)
    player_count = int(os.getenv("LORECRAFT_LOAD_TEST_PLAYERS", str(_DEFAULT_PLAYERS)))
    # Per-command arrival jitter: 0 (default) fires everyone in lockstep — the
    # worst-case thundering herd. A non-zero value spreads command arrivals over
    # 0..jitter ms, approximating realistic think-time between commands.
    jitter_ms = int(os.getenv("LORECRAFT_LOAD_TEST_JITTER_MS", "0"))

    server = simulation_server_factory(rng_seed=scenario.rng_seed)
    report = fan_out_scenario(
        server, scenario, players=player_count, jitter_ms=jitter_ms
    )

    print(
        f"\nLoad test — {report['players']} concurrent players × "
        f"{report['commands_per_player']} commands ({report['total_commands']} total), "
        f"jitter={jitter_ms} ms, scenario={scenario_path.name}\n"
        f"  p50={report['p50_ms']} ms  p95={report['p95_ms']} ms  "
        f"p99={report['p99_ms']} ms  max={report['max_ms']} ms"
    )
    out_path = os.getenv("LORECRAFT_LOAD_TEST_JSON")
    if out_path:
        Path(out_path).write_text(
            json.dumps({"scenario": scenario_path.name, **report}, indent=2)
        )

    assert report["total_commands"] == player_count * len(scenario.commands)
    # Sanity gate: catches a hung/broken server or a gross regression without
    # being so tight it flakes on a loaded CI box.
    assert report["p99_ms"] < _LATENCY_CEILING_MS
