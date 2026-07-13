"""Audit log regression testing (Sprint 12 / architecture.md §25; data-driven
by scenario replay since Sprint 43.1; multi-scenario since the Rust-port
Phase 0 evidence gate).

Golden-path command scripts live in checked-in scenario files (the Sprint 43
record/playback format) instead of hard-coded lists, and are replayed through
`tests.simulation.replay.replay_scenario`. Two guards run for *every* scenario
in `_SCENARIOS`:

1. **Determinism** — the same scenario against two independent fresh servers
   must produce the same normalised audit trail (same event types, summaries,
   targets, rooms, severities, in order; run-specific IDs/timestamps
   excluded).
2. **Golden diff** — the trail must match the checked-in `<name>.audit.json`.
   A diff here means a code or world change altered what the session records —
   either a regression, or an intentional change: regenerate with

       LORECRAFT_UPDATE_GOLDENS=1 make test-simulation

   and review the goldens' diff in the commit.

Scenarios:

- `golden_path` — the original mutation-heavy Ashmoore session (look, move,
  take, quest).
- `look_only` — a single read-only `look`, the tight parity slice added for
  the Rust-port `look` conversion.
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

# Scenario stems replayed by both guards. Each `<name>` resolves to
# `<name>.json` (script) + `<name>.audit.json` (golden trail).
_SCENARIOS = ("golden_path", "look_only")


def _scenario_path(name: str) -> Path:
    return _SCENARIOS_DIR / f"{name}.json"


def _golden_path(name: str) -> Path:
    return _SCENARIOS_DIR / f"{name}.audit.json"


@pytest.mark.parametrize("scenario_name", _SCENARIOS)
def test_same_scenario_produces_the_same_normalized_audit_trail(
    scenario_name: str,
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """Regression guard: replaying a scenario twice, against two independent
    fresh servers, should record the same sequence of audit events (modulo
    run-specific IDs/timestamps). A divergence here means a code change made
    command handling non-deterministic for an identical script — worth
    investigating before merging."""
    scenario = load_scenario(_scenario_path(scenario_name))
    first_run = asyncio.run(
        replay_scenario(simulation_server_factory(rng_seed=scenario.rng_seed), scenario)
    )
    second_run = asyncio.run(
        replay_scenario(simulation_server_factory(rng_seed=scenario.rng_seed), scenario)
    )

    assert first_run == second_run
    assert len(first_run) > 0


@pytest.mark.parametrize("scenario_name", _SCENARIOS)
def test_scenario_replay_matches_checked_in_golden(
    scenario_name: str,
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """Golden diff: the normalised trail must match the checked-in capture.

    Unlike the run-vs-run determinism guard above, this catches changes
    *between code versions* — the point of record/playback regression. On an
    intentional behavior/world change, regenerate with
    LORECRAFT_UPDATE_GOLDENS=1 and review the goldens' diff."""
    scenario = load_scenario(_scenario_path(scenario_name))
    golden_path = _golden_path(scenario_name)
    trail = asyncio.run(
        replay_scenario(simulation_server_factory(rng_seed=scenario.rng_seed), scenario)
    )

    if os.getenv("LORECRAFT_UPDATE_GOLDENS") == "1":
        golden_path.write_text(json.dumps(trail, indent=2) + "\n")

    assert golden_path.exists(), (
        f"no golden audit trail checked in for {scenario_name!r} — generate one "
        "with LORECRAFT_UPDATE_GOLDENS=1 make test-simulation"
    )
    golden = json.loads(golden_path.read_text())
    assert trail == golden
