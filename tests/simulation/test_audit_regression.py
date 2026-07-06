"""Audit log regression testing (Sprint 12 / architecture.md §25; data-driven
by scenario replay since Sprint 43.1).

The golden-path command script now lives in a checked-in scenario file
(`scenarios/golden_path.json`, the Sprint 43 record/playback format) instead
of a hard-coded list, and is replayed through
`tests.simulation.replay.replay_scenario`. Two guards:

1. **Determinism** — the same scenario against two independent fresh servers
   must produce the same normalised audit trail (same event types, summaries,
   targets, rooms, severities, in order; run-specific IDs/timestamps
   excluded).
2. **Golden diff** — the trail must match the checked-in
   `scenarios/golden_path.audit.json`. A diff here means a code or world
   change altered what the golden-path session records — either a regression,
   or an intentional change: regenerate with

       LORECRAFT_UPDATE_GOLDENS=1 make test-simulation

   and review the golden's diff in the commit.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from lorecraft.tools.session_replay import load_scenario
from tests.simulation.conftest import SimulationServer
from tests.simulation.replay import replay_scenario

pytestmark = pytest.mark.simulation

_SCENARIOS_DIR = Path(__file__).parent / "scenarios"
_SCENARIO_PATH = _SCENARIOS_DIR / "golden_path.json"
_GOLDEN_AUDIT_PATH = _SCENARIOS_DIR / "golden_path.audit.json"


def test_same_scenario_produces_the_same_normalized_audit_trail(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """Regression guard: replaying the golden-path scenario twice, against two
    independent fresh servers, should record the same sequence of audit
    events (modulo run-specific IDs/timestamps). A divergence here means a
    code change made command handling non-deterministic for an identical
    script — worth investigating before merging."""
    scenario = load_scenario(_SCENARIO_PATH)
    first_run = asyncio.run(
        replay_scenario(simulation_server_factory(rng_seed=scenario.rng_seed), scenario)
    )
    second_run = asyncio.run(
        replay_scenario(simulation_server_factory(rng_seed=scenario.rng_seed), scenario)
    )

    assert first_run == second_run
    assert len(first_run) > 0


def test_scenario_replay_matches_checked_in_golden(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """Golden diff: the normalised trail must match the checked-in capture.

    Unlike the run-vs-run determinism guard above, this catches changes
    *between code versions* — the point of record/playback regression. On an
    intentional behavior/world change, regenerate with
    LORECRAFT_UPDATE_GOLDENS=1 and review the golden's diff."""
    scenario = load_scenario(_SCENARIO_PATH)
    trail = asyncio.run(
        replay_scenario(simulation_server_factory(rng_seed=scenario.rng_seed), scenario)
    )

    if os.getenv("LORECRAFT_UPDATE_GOLDENS") == "1":
        _GOLDEN_AUDIT_PATH.write_text(json.dumps(trail, indent=2) + "\n")

    assert _GOLDEN_AUDIT_PATH.exists(), (
        "no golden audit trail checked in — generate one with "
        "LORECRAFT_UPDATE_GOLDENS=1 make test-simulation"
    )
    golden = json.loads(_GOLDEN_AUDIT_PATH.read_text())
    assert trail == golden
