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
    LORECRAFT_LOAD_TEST_PLAYERS=50 \\
    LORECRAFT_LOAD_TEST_SCENARIO=tests/simulation/scenarios/load_world_hunt.json \\
    LORECRAFT_LOAD_TEST_OPEN_HUNT=harvest_trinkets \\
    LORECRAFT_LOAD_TEST_LATENCY_CEILING_MS=3000 \\
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
import platform
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lorecraft import __version__
from lorecraft.tools.session_replay import load_scenario
from tests.simulation.conftest import SimulationServer
from tests.simulation.replay import fan_out_scenario

pytestmark = pytest.mark.simulation

_REPO_ROOT = Path(__file__).resolve().parents[2]
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
    open_hunt_id = os.getenv("LORECRAFT_LOAD_TEST_OPEN_HUNT", "").strip()
    latency_ceiling_ms = float(
        os.getenv("LORECRAFT_LOAD_TEST_LATENCY_CEILING_MS", str(_LATENCY_CEILING_MS))
    )

    server = simulation_server_factory(rng_seed=scenario.rng_seed)
    if open_hunt_id:
        server.open_hunt(open_hunt_id)
    report = fan_out_scenario(
        server, scenario, players=player_count, jitter_ms=jitter_ms
    )

    print(
        f"\nLoad test — {report['players']} concurrent players × "
        f"{report['commands_per_player']} commands ({report['total_commands']} total), "
        f"jitter={jitter_ms} ms, scenario={scenario_path.name}, "
        f"open_hunt={open_hunt_id or '-'}, ceiling={latency_ceiling_ms} ms\n"
        f"  p50={report['p50_ms']} ms  p95={report['p95_ms']} ms  "
        f"p99={report['p99_ms']} ms  max={report['max_ms']} ms"
    )
    out_path = os.getenv("LORECRAFT_LOAD_TEST_JSON")
    if out_path:
        Path(out_path).write_text(
            json.dumps({"scenario": scenario_path.name, **report}, indent=2)
        )
    history_path = os.getenv("LORECRAFT_LOAD_TEST_HISTORY")
    if history_path:
        _append_history_record(
            Path(history_path),
            report=report,
            scenario_path=scenario_path,
            open_hunt_id=open_hunt_id,
            latency_ceiling_ms=latency_ceiling_ms,
        )

    assert report["total_commands"] == player_count * len(scenario.commands)
    # Sanity gate: catches a hung/broken server or a gross regression without
    # being so tight it flakes on a loaded CI box.
    assert report["p99_ms"] < latency_ceiling_ms


def _append_history_record(
    history_path: Path,
    *,
    report: dict[str, float | int],
    scenario_path: Path,
    open_hunt_id: str,
    latency_ceiling_ms: float,
) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "label": os.getenv("LORECRAFT_LOAD_TEST_LABEL", ""),
        "notes": os.getenv("LORECRAFT_LOAD_TEST_NOTES", ""),
        "version": __version__,
        "changelog": _changelog_heading(__version__),
        "git": _git_metadata(),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "scenario": str(scenario_path),
        "open_hunt": open_hunt_id or None,
        "latency_ceiling_ms": latency_ceiling_ms,
        "passed_latency_gate": report["p99_ms"] < latency_ceiling_ms,
        "db_query_log_enabled": _env_bool("LORECRAFT_DB_QUERY_LOG_ENABLED", True),
        **report,
    }
    with history_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, sort_keys=True) + "\n")


def _changelog_heading(version: str) -> str:
    changelog_path = _REPO_ROOT / "CHANGELOG.md"
    if not changelog_path.exists():
        return f"[{version}]"
    prefix = f"## [{version}]"
    for line in changelog_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.removeprefix("## ").strip()
    return f"[{version}]"


def _git_metadata() -> dict[str, str | bool]:
    status = _git("status", "--short")
    return {
        "branch": _git("branch", "--show-current"),
        "commit": _git("rev-parse", "--short=12", "HEAD"),
        "dirty": bool(status),
    }


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
