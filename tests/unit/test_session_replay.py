"""Session record & scenario format (Sprint 43.1, `lorecraft.tools.session_replay`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_audit_tables
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.types import JsonObject
from lorecraft.tools.session_replay import (
    Scenario,
    ScenarioCommand,
    latency_report,
    load_scenario,
    main,
    normalize_events,
    percentile,
    record_scenario,
    save_scenario,
)


def _audit_event(
    *,
    actor_id: str = "player-1",
    event_type: str = "command_executed",
    real_time: float,
    raw: str | None = None,
    summary: str = "",
) -> AuditEvent:
    payload: JsonObject = {}
    if raw is not None:
        payload["raw"] = raw
    return AuditEvent(
        transaction_id="txn",
        correlation_id="corr",
        actor_id=actor_id,
        event_type=event_type,
        source_type="player",
        room_id="village_square",
        game_time=0.0,
        real_time=real_time,
        summary=summary,
        payload_json=payload,
    )


def _make_audit_db(path: Path, events: list[AuditEvent]) -> None:
    engine = create_engine(f"sqlite:///{path}")
    create_audit_tables(engine)
    with Session(engine) as session:
        for event in events:
            session.add(event)
        session.commit()


def test_record_projects_command_events_in_order_with_t_deltas(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _make_audit_db(
        db,
        [
            _audit_event(real_time=100.0, raw="look"),
            # Non-command events for the same actor are not part of the script.
            _audit_event(event_type="item_taken", real_time=100.5),
            # Other actors' commands don't leak into this actor's recording.
            _audit_event(actor_id="player-2", real_time=101.0, raw="go north"),
            _audit_event(event_type="command_blocked", real_time=102.5, raw="dance"),
            _audit_event(real_time=104.0, raw="go east"),
        ],
    )

    scenario = record_scenario(db, "player-1", description="test session")

    assert scenario.actors == ["player-1"]
    assert scenario.description == "test session"
    assert [(c.t, c.raw) for c in scenario.commands] == [
        (0.0, "look"),
        (2.5, "dance"),
        (4.0, "go east"),
    ]


def test_record_since_drops_earlier_events(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _make_audit_db(
        db,
        [
            _audit_event(real_time=100.0, raw="look"),
            _audit_event(real_time=200.0, raw="go east"),
        ],
    )

    scenario = record_scenario(db, "player-1", since=150.0)

    assert [(c.t, c.raw) for c in scenario.commands] == [(0.0, "go east")]


def test_record_with_no_command_events_raises(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _make_audit_db(db, [_audit_event(event_type="item_taken", real_time=1.0)])

    with pytest.raises(ValueError, match="no command events"):
        record_scenario(db, "player-1")


def test_scenario_json_round_trip(tmp_path: Path) -> None:
    scenario = Scenario(
        description="round trip",
        rng_seed=7,
        actors=["player-1"],
        commands=[
            ScenarioCommand(t=0.0, actor="player-1", raw="look"),
            ScenarioCommand(t=1.5, actor="player-1", raw="go east"),
        ],
    )
    path = tmp_path / "scenario.json"

    save_scenario(scenario, path)
    loaded = load_scenario(path)

    assert loaded == scenario


def test_load_rejects_unknown_scenario_version(tmp_path: Path) -> None:
    path = tmp_path / "scenario.json"
    path.write_text('{"version": 99, "actors": [], "commands": []}')

    with pytest.raises(ValueError, match="unsupported scenario version"):
        load_scenario(path)


def test_commands_for_filters_by_actor() -> None:
    scenario = Scenario(
        actors=["a", "b"],
        commands=[
            ScenarioCommand(t=0.0, actor="a", raw="look"),
            ScenarioCommand(t=0.5, actor="b", raw="who"),
            ScenarioCommand(t=1.0, actor="a", raw="go east"),
        ],
    )

    assert [c.raw for c in scenario.commands_for("a")] == ["look", "go east"]


def test_normalize_events_keeps_only_replay_stable_fields() -> None:
    event = _audit_event(real_time=1.0, raw="look", summary="Looked around")

    assert normalize_events([event]) == [
        {
            "event_type": "command_executed",
            "summary": "Looked around",
            "target_id": None,
            "room_id": "village_square",
            "severity": "INFO",
        }
    ]


def test_percentile_nearest_rank() -> None:
    ordered = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

    assert percentile(ordered, 0.50) == 6.0
    assert percentile(ordered, 0.99) == 10.0
    assert percentile([], 0.50) == 0.0


def test_latency_report_shape_matches_load_test() -> None:
    report = latency_report(
        [30.0, 10.0, 20.0], players=3, commands_per_player=1, jitter_ms=5
    )

    assert report == {
        "players": 3,
        "commands_per_player": 1,
        "total_commands": 3,
        "jitter_ms": 5,
        "p50_ms": 20.0,
        "p95_ms": 30.0,
        "p99_ms": 30.0,
        "max_ms": 30.0,
    }


def test_latency_report_empty_is_all_zeros() -> None:
    report = latency_report([], players=0, commands_per_player=0)

    assert report["total_commands"] == 0
    assert report["p50_ms"] == 0.0
    assert report["max_ms"] == 0.0


def test_cli_record_writes_scenario_file(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _make_audit_db(db, [_audit_event(real_time=100.0, raw="look")])
    out = tmp_path / "scenario.json"

    exit_code = main(
        [
            "record",
            "--audit-db",
            str(db),
            "--actor",
            "player-1",
            "-o",
            str(out),
            "--rng-seed",
            "1",
        ]
    )

    assert exit_code == 0
    scenario = load_scenario(out)
    assert scenario.rng_seed == 1
    assert [c.raw for c in scenario.commands] == ["look"]


def test_cli_record_missing_db_fails(tmp_path: Path) -> None:
    exit_code = main(
        [
            "record",
            "--audit-db",
            str(tmp_path / "missing.db"),
            "--actor",
            "player-1",
            "-o",
            str(tmp_path / "out.json"),
        ]
    )

    assert exit_code == 1
