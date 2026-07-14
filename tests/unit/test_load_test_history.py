from __future__ import annotations

import json
from pathlib import Path

from lorecraft import __version__
from tests.simulation.test_load import _append_history_record


def test_append_history_record_stamps_version_and_run_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    history_path = tmp_path / "history.jsonl"
    report: dict[str, float | int] = {
        "players": 50,
        "commands_per_player": 147,
        "jitter_ms": 0,
        "total_commands": 7350,
        "p50_ms": 935.112,
        "p95_ms": 1498.078,
        "p99_ms": 1761.204,
        "max_ms": 1907.113,
    }
    monkeypatch.setenv("LORECRAFT_LOAD_TEST_LABEL", "nightly")
    monkeypatch.setenv("LORECRAFT_LOAD_TEST_NOTES", "post-feature run")
    monkeypatch.setenv("LORECRAFT_DB_QUERY_LOG_ENABLED", "false")

    _append_history_record(
        history_path,
        report=report,
        scenario_path=Path("tests/simulation/scenarios/load_world_hunt.json"),
        open_hunt_id="harvest_trinkets",
        latency_ceiling_ms=3000.0,
    )

    record = json.loads(history_path.read_text(encoding="utf-8"))
    assert record["version"] == __version__
    assert record["changelog"].startswith(f"[{__version__}]")
    assert record["label"] == "nightly"
    assert record["notes"] == "post-feature run"
    assert record["scenario"] == "tests/simulation/scenarios/load_world_hunt.json"
    assert record["open_hunt"] == "harvest_trinkets"
    assert record["db_query_log_enabled"] is False
    assert record["passed_latency_gate"] is True
    assert record["p99_ms"] == 1761.204
    assert record["git"]["commit"]
