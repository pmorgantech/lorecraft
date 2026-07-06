"""Mixed-scenario soak test (Sprint 43.3).

Distinct recorded sessions replay **concurrently** against one live server —
the golden-path quest session interleaving with the read-heavy load loop —
each looped `LORECRAFT_SOAK_REPEATS` times. Different behaviors contending
over shared world state (dialogue sessions, the market coin, movement
broadcasts) is what surfaces crashes and contention a single lockstep script
can't; the assertion is simply that every command completed and latency
stayed sane.

Marked `simulation`, excluded from the default suite. The checked-in default
(2 repeats) keeps CI fast; a real soak is opt-in:

    make test-simulation                       # short mix, CI default
    LORECRAFT_SOAK_REPEATS=50 \\
        .venv/bin/python -m pytest -s tests/simulation/test_soak.py -m simulation

(or dispatch the CI workflow with a `soak_repeats` input — see
.github/workflows/ci.yml). `-s` surfaces the printed summary;
`LORECRAFT_SOAK_JSON` writes it as machine-readable JSON.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from lorecraft.tools.session_replay import load_scenario
from tests.simulation.conftest import SimulationServer
from tests.simulation.replay import mix_scenarios

pytestmark = pytest.mark.simulation

_SCENARIOS_DIR = Path(__file__).parent / "scenarios"
_MIX = ["golden_path.json", "load_default.json"]
_DEFAULT_REPEATS = 2
_LATENCY_CEILING_MS = 2000.0  # generous — trips only on a hang/gross regression


def test_mixed_scenarios_soak(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    repeats = int(os.getenv("LORECRAFT_SOAK_REPEATS") or _DEFAULT_REPEATS)
    jitter_ms = int(os.getenv("LORECRAFT_LOAD_TEST_JITTER_MS", "0"))
    scenarios = [load_scenario(_SCENARIOS_DIR / name) for name in _MIX]

    server = simulation_server_factory(rng_seed=scenarios[0].rng_seed)
    report = mix_scenarios(server, scenarios, repeats=repeats, jitter_ms=jitter_ms)

    print(
        f"\nSoak — {report['scenarios']} mixed scenarios × {repeats} repeats "
        f"({report['total_commands']} commands), jitter={jitter_ms} ms\n"
        f"  p50={report['p50_ms']} ms  p95={report['p95_ms']} ms  "
        f"p99={report['p99_ms']} ms  max={report['max_ms']} ms"
    )
    out_path = os.getenv("LORECRAFT_SOAK_JSON")
    if out_path:
        Path(out_path).write_text(json.dumps({"mix": _MIX, **report}, indent=2))

    # Every recorded command across the whole mix got a command_result back —
    # a hung/crashed server would have timed out inside the replay instead.
    expected = repeats * sum(len(scenario.commands) for scenario in scenarios)
    assert report["total_commands"] == expected
    assert report["p99_ms"] < _LATENCY_CEILING_MS
