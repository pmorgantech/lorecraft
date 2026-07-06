from typing import cast

import pytest
from sqlmodel import Session, create_engine

from lorecraft.analytics import (
    InvalidRangeError,
    activity_by_hour,
    command_latency_percentiles,
    npc_interaction_counts,
    operation_latency_percentiles,
    operation_timeline,
    parse_range,
    player_hours,
    quest_completion_counts,
    top_commands,
)
from lorecraft.db import create_tables
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.session import PlayerSession
from lorecraft.types import JsonObject


def _game_engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def _audit_engine():
    audit_engine = create_engine("sqlite://")
    create_tables(game_engine=create_engine("sqlite://"), audit_engine=audit_engine)
    return audit_engine


def _event(
    *,
    event_type: str,
    real_time: float,
    target_id: str | None = None,
    payload: JsonObject | None = None,
) -> AuditEvent:
    return AuditEvent(
        transaction_id="tx-1",
        correlation_id="corr-1",
        actor_id="player-1",
        event_type=event_type,
        source_type="player",
        target_id=target_id,
        room_id="square",
        game_time=0.0,
        real_time=real_time,
        summary="",
        payload_json=cast(JsonObject, payload or {}),
    )


@pytest.mark.parametrize(
    "range_str,expected_seconds",
    [("24h", 86400), ("7d", 604800), ("2w", 1209600), ("30m", 1800)],
)
def test_parse_range_valid(range_str: str, expected_seconds: int) -> None:
    assert parse_range(range_str) == expected_seconds


def test_parse_range_rejects_invalid_format() -> None:
    with pytest.raises(InvalidRangeError):
        parse_range("banana")


def test_top_commands_counts_by_verb_within_range() -> None:
    engine = _audit_engine()
    now = 1_000_000.0
    with Session(engine) as session:
        session.add(
            _event(
                event_type=GameEvent.COMMAND_EXECUTED.value,
                real_time=now,
                payload={"verb": "look"},
            )
        )
        session.add(
            _event(
                event_type=GameEvent.COMMAND_EXECUTED.value,
                real_time=now,
                payload={"verb": "look"},
            )
        )
        session.add(
            _event(
                event_type=GameEvent.COMMAND_EXECUTED.value,
                real_time=now,
                payload={"verb": "take"},
            )
        )
        # Outside range — excluded.
        session.add(
            _event(
                event_type=GameEvent.COMMAND_EXECUTED.value,
                real_time=now - 1_000_000,
                payload={"verb": "take"},
            )
        )
        # Wrong event type — excluded.
        session.add(
            _event(
                event_type=GameEvent.COMMAND_BLOCKED.value,
                real_time=now,
                payload={"verb": "take"},
            )
        )
        session.commit()

        result = top_commands(session, since=now - 100, limit=20)

    assert result == [{"verb": "look", "count": 2}, {"verb": "take", "count": 1}]


def test_npc_interaction_counts_scoped_to_single_npc() -> None:
    engine = _audit_engine()
    now = 1_000_000.0
    with Session(engine) as session:
        session.add(
            _event(
                event_type=GameEvent.NPC_ATTACKED.value,
                real_time=now,
                target_id="npc-mira",
            )
        )
        session.add(
            _event(
                event_type=GameEvent.NPC_ATTACKED.value,
                real_time=now,
                target_id="npc-mira",
            )
        )
        session.add(
            _event(
                event_type=GameEvent.NPC_ATTACKED.value,
                real_time=now,
                target_id="npc-aldric",
            )
        )
        session.commit()

        all_counts = npc_interaction_counts(session, since=now - 100)
        mira_only = npc_interaction_counts(session, since=now - 100, npc_id="npc-mira")

    assert {c["npc_id"]: c["interactions"] for c in all_counts} == {
        "npc-mira": 2,
        "npc-aldric": 1,
    }
    assert mira_only == [{"npc_id": "npc-mira", "interactions": 2}]


def test_quest_completion_counts_by_quest_id() -> None:
    engine = _audit_engine()
    now = 1_000_000.0
    with Session(engine) as session:
        session.add(
            _event(
                event_type=GameEvent.QUEST_COMPLETED.value,
                real_time=now,
                payload={"quest_id": "find_sword"},
            )
        )
        session.add(
            _event(
                event_type=GameEvent.QUEST_COMPLETED.value,
                real_time=now,
                payload={"quest_id": "find_sword"},
            )
        )
        session.commit()

        result = quest_completion_counts(session, since=now - 100)

    assert result == [{"quest_id": "find_sword", "completions": 2}]


def test_command_latency_percentiles_computed_from_duration_ms() -> None:
    engine = _audit_engine()
    now = 1_000_000.0
    with Session(engine) as session:
        for duration_ms in [10.0, 20.0, 30.0, 40.0, 100.0]:
            session.add(
                _event(
                    event_type=GameEvent.COMMAND_EXECUTED.value,
                    real_time=now,
                    payload={"verb": "look", "duration_ms": duration_ms},
                )
            )
        # Outside range — excluded.
        session.add(
            _event(
                event_type=GameEvent.COMMAND_EXECUTED.value,
                real_time=now - 1_000_000,
                payload={"verb": "look", "duration_ms": 9999.0},
            )
        )
        session.commit()

        result = command_latency_percentiles(session, since=now - 100)

    assert result["count"] == 5
    assert result["p50"] == 30.0
    assert result["p99"] == 100.0


def test_command_latency_percentiles_empty_when_no_events() -> None:
    engine = _audit_engine()
    with Session(engine) as session:
        result = command_latency_percentiles(session, since=0.0)

    assert result == {"p50": 0.0, "p95": 0.0, "p99": 0.0, "count": 0}


def test_operation_latency_percentiles_grouped_by_operation() -> None:
    engine = _audit_engine()
    now = 1_000_000.0
    with Session(engine) as session:
        for parse_ms in [1.0, 2.0, 3.0, 4.0, 5.0]:
            session.add(
                _event(
                    event_type=GameEvent.COMMAND_EXECUTED.value,
                    real_time=now,
                    payload={
                        "verb": "look",
                        "duration_ms": parse_ms * 10,  # command_handler timing
                        "perf": {
                            "command_parse": parse_ms,
                            "condition_evaluate": 0.01,
                            "db_commit": 0.02,
                        },
                    },
                )
            )
        # Outside range — excluded from every operation.
        session.add(
            _event(
                event_type=GameEvent.COMMAND_EXECUTED.value,
                real_time=now - 1_000_000,
                payload={
                    "verb": "look",
                    "duration_ms": 9999.0,
                    "perf": {"command_parse": 9999.0},
                },
            )
        )
        session.commit()

        result = operation_latency_percentiles(session, since=now - 100)

    assert set(result) == {
        "command_handler",
        "command_parse",
        "condition_evaluate",
        "db_commit",
    }
    assert result["command_parse"]["count"] == 5
    assert result["command_parse"]["p50"] == 3.0
    assert result["command_parse"]["p99"] == 5.0
    # The top-level duration_ms surfaces as the command_handler operation.
    assert result["command_handler"]["count"] == 5
    assert result["command_handler"]["p50"] == 30.0


def test_operation_latency_percentiles_includes_events_without_perf() -> None:
    # Pre-35.3 COMMAND_EXECUTED events (no perf breakdown) still contribute
    # their command_handler timing.
    engine = _audit_engine()
    now = 1_000_000.0
    with Session(engine) as session:
        session.add(
            _event(
                event_type=GameEvent.COMMAND_EXECUTED.value,
                real_time=now,
                payload={"verb": "look", "duration_ms": 15.0},
            )
        )
        session.commit()

        result = operation_latency_percentiles(session, since=now - 100)

    assert set(result) == {"command_handler"}
    assert result["command_handler"]["count"] == 1
    assert result["command_handler"]["p50"] == 15.0


def test_operation_latency_percentiles_empty_when_no_events() -> None:
    engine = _audit_engine()
    with Session(engine) as session:
        result = operation_latency_percentiles(session, since=0.0)

    assert result == {}


def test_player_hours_sums_session_duration() -> None:
    engine = _game_engine()
    now = 1_000_000.0
    with Session(engine) as session:
        session.add(
            PlayerSession(
                id="sess-1",
                player_id="player-1",
                connected_at=now - 3600,
                disconnected_at=now,
            )
        )
        session.add(
            PlayerSession(
                id="sess-2",
                player_id="player-1",
                connected_at=now - 1800,
                disconnected_at=now,
            )
        )
        # Still connected — counted through `now`.
        session.add(
            PlayerSession(
                id="sess-3",
                player_id="player-2",
                connected_at=now - 900,
                disconnected_at=None,
            )
        )
        session.commit()

        result = player_hours(session, since=now - 10000, now=now)

    result_map = {r["player_id"]: r["hours"] for r in result}
    assert result_map["player-1"] == 1.5
    assert result_map["player-2"] == 0.25


def test_operation_timeline_returns_recent_commands_newest_first() -> None:
    engine = _audit_engine()
    with Session(engine) as session:
        for i, verb in enumerate(["look", "go", "take"]):
            session.add(
                _event(
                    event_type=GameEvent.COMMAND_EXECUTED.value,
                    real_time=100.0 + i,
                    payload={"verb": verb, "duration_ms": 1.5 + i},
                )
            )
        session.commit()

        timeline = operation_timeline(session, limit=10)

    assert [row["verb"] for row in timeline] == ["take", "go", "look"]  # newest first
    assert timeline[0]["duration_ms"] == 3.5
    assert timeline[0]["actor_id"] == "player-1"


def test_operation_timeline_respects_limit() -> None:
    engine = _audit_engine()
    with Session(engine) as session:
        for i in range(5):
            session.add(
                _event(
                    event_type=GameEvent.COMMAND_EXECUTED.value,
                    real_time=100.0 + i,
                    payload={"verb": "look"},
                )
            )
        session.commit()
        assert len(operation_timeline(session, limit=2)) == 2


def test_activity_by_hour_buckets_all_24_hours() -> None:
    import time as _time

    engine = _audit_engine()
    # Two events in the same UTC hour, one in another.
    base = _time.gmtime(0)  # hour 0
    assert base.tm_hour == 0
    with Session(engine) as session:
        session.add(
            _event(event_type=GameEvent.COMMAND_EXECUTED.value, real_time=0.0)
        )  # hour 0
        session.add(
            _event(event_type=GameEvent.COMMAND_EXECUTED.value, real_time=60.0)
        )  # hour 0
        session.add(
            _event(event_type=GameEvent.COMMAND_EXECUTED.value, real_time=3600.0)
        )  # hour 1
        session.commit()

        heatmap = activity_by_hour(session, since=-1.0)

    assert len(heatmap) == 24
    by_hour = {row["hour"]: row["count"] for row in heatmap}
    assert by_hour[0] == 2
    assert by_hour[1] == 1
    assert by_hour[5] == 0  # dense: idle hours present with count 0
