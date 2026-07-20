"""Integration tests for admin REST API: audit log, system health, analytics, request
tracing, and crash reporting (observability endpoints)."""

from __future__ import annotations

import time
from typing import Any

import anyio
from sqlmodel import Session

from lorecraft.engine.models.audit import AuditEvent
from lorecraft.main import create_app

from tests.integration._admin_api_support import (
    _SETTINGS,
    _access_token,
    _http,
    _lifespan,
    _make_engines,
)

# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_audit_log_returns_list() -> None:
    anyio.run(_test_audit_log)


async def _test_audit_log() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/audit", token=token)
    assert status == 200
    assert isinstance(data, list)


def test_audit_facets_return_counts() -> None:
    anyio.run(_test_audit_facets)


async def _test_audit_facets() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    with Session(audit_engine) as session:
        session.add(
            AuditEvent(
                transaction_id="txn-facet",
                correlation_id="corr-facet",
                actor_id="player-1",
                event_type="command_executed",
                source_type="player",
                room_id="village_square",
                game_time=0.0,
                real_time=time.time(),
                severity="INFO",
                summary="Command executed: look",
            )
        )
        session.commit()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/audit/facets", token=token)
    assert status == 200
    assert {"value": "command_executed", "count": 1} in data["event_types"]


def test_audit_export_json_honors_filters() -> None:
    anyio.run(_test_audit_export_json)


async def _test_audit_export_json() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    with Session(audit_engine) as session:
        session.add(
            AuditEvent(
                transaction_id="txn-export",
                correlation_id="corr-export",
                actor_id="player-1",
                event_type="admin_action",
                source_type="admin",
                room_id="",
                game_time=0.0,
                real_time=time.time(),
                severity="WARNING",
                summary="Admin action exported",
            )
        )
        session.add(
            AuditEvent(
                transaction_id="txn-export-other",
                correlation_id="corr-export-other",
                actor_id="player-2",
                event_type="command_executed",
                source_type="player",
                room_id="village_square",
                game_time=0.0,
                real_time=time.time(),
                severity="INFO",
                summary="Command executed: look",
            )
        )
        session.commit()
    async with _lifespan(app):
        status, body = await _http(
            app,
            "GET",
            "/admin/audit/export?format=json&event_type=admin_action",
            token=token,
        )
    assert status == 200
    assert [row["summary"] for row in body] == ["Admin action exported"]


def test_system_health_and_scheduler_endpoints() -> None:
    anyio.run(_test_system_health_and_scheduler)


async def _test_system_health_and_scheduler() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        health_status, health = await _http(
            app, "GET", "/admin/system/health", token=token
        )
        sched_status, jobs = await _http(
            app, "GET", "/admin/system/scheduler", token=token
        )
    assert health_status == 200
    assert "websocket_connections" in health
    assert "pending_scheduler_jobs" in health
    assert sched_status == 200
    assert isinstance(jobs, list)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def test_analytics_endpoints_return_empty_lists_with_no_data() -> None:
    anyio.run(_test_analytics_endpoints_empty)


async def _test_analytics_endpoints_empty() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        for path in (
            "/admin/analytics/commands",
            "/admin/analytics/npcs",
            "/admin/analytics/quests",
            "/admin/analytics/quest-funnel",
            "/admin/analytics/player-hours",
        ):
            status, data = await _http(app, "GET", path, token=token)
            assert status == 200
            assert data == []


def test_analytics_latency_returns_zeroed_percentiles_with_no_data() -> None:
    anyio.run(_test_analytics_latency_empty)


async def _test_analytics_latency_empty() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/analytics/latency", token=token)
        assert status == 200
        assert data == {"p50": 0.0, "p95": 0.0, "p99": 0.0, "count": 0}


def test_analytics_performance_returns_empty_by_operation_with_no_data() -> None:
    anyio.run(_test_analytics_performance_empty)


async def _test_analytics_performance_empty() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app, "GET", "/admin/analytics/performance", token=token
        )
        assert status == 200
        assert data == {}


def test_analytics_dashboard_returns_combined_payload() -> None:
    anyio.run(_test_analytics_dashboard)


async def _test_analytics_dashboard() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app, "GET", "/admin/analytics/dashboard", token=token
        )
        assert status == 200
        assert set(data) == {
            "range",
            "latency_by_operation",
            "timeline",
            "heatmap",
            "top_commands",
            "npc_interactions",
            "quest_funnel",
        }
        # Heatmap is always a dense 24-bucket histogram.
        assert isinstance(data["heatmap"], list) and len(data["heatmap"]) == 24
        assert isinstance(data["timeline"], list)
        assert data["top_commands"] == []
        assert data["npc_interactions"] == []
        assert data["quest_funnel"] == []


def test_analytics_dashboard_requires_auth() -> None:
    anyio.run(_test_analytics_dashboard_unauth)


async def _test_analytics_dashboard_unauth() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, _data = await _http(app, "GET", "/admin/analytics/dashboard")
        assert status in (401, 403)


def test_analytics_invalid_range_returns_400() -> None:
    anyio.run(_test_analytics_invalid_range)


async def _test_analytics_invalid_range() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(
            app, "GET", "/admin/analytics/commands?range=notarange", token=token
        )
        assert status == 400
        assert "detail" in data


# ---------------------------------------------------------------------------
# Request tracing (Sprint 57.2)
# ---------------------------------------------------------------------------


def test_trace_endpoint_returns_404_for_unknown_transaction() -> None:
    anyio.run(_test_trace_unknown)


async def _test_trace_unknown() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, _data = await _http(
            app, "GET", "/admin/trace/never-seen-txn-id", token=token
        )
        assert status == 404


def test_trace_endpoint_returns_captured_spans() -> None:
    anyio.run(_test_trace_returns_spans)


async def _test_trace_returns_spans() -> None:
    from lorecraft.observability import bind_transaction_context, record_span

    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    with bind_transaction_context("txn-admin-trace-1", "corr-admin-trace-1"):
        record_span("command_parse", 1.25)
        record_span("db_commit", 2.5)
    async with _lifespan(app):
        status, data = await _http(
            app, "GET", "/admin/trace/txn-admin-trace-1", token=token
        )
        assert status == 200
        assert [span["name"] for span in data] == ["command_parse", "db_commit"]
        assert data[0]["duration_ms"] == 1.25


def test_trace_endpoint_requires_auth() -> None:
    anyio.run(_test_trace_requires_auth)


async def _test_trace_requires_auth() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, _data = await _http(app, "GET", "/admin/trace/anything")
        assert status in (401, 403)


# ---------------------------------------------------------------------------
# Crash reports (Sprint 57.4)
# ---------------------------------------------------------------------------


def _seed_crash(audit_engine: Any, **overrides: Any) -> None:
    from lorecraft.engine.models.audit import CrashReport

    defaults: dict[str, Any] = {
        "transaction_id": "txn-crash-1",
        "correlation_id": "corr-crash-1",
        "player_id": "player-1",
        "command_text": "go north",
        "stack_trace": "Traceback (most recent call last):\nRuntimeError: boom",
        "real_time": time.time(),
    }
    defaults.update(overrides)
    with Session(audit_engine) as session:
        session.add(CrashReport(**defaults))
        session.commit()


def test_list_crashes_returns_empty_with_no_data() -> None:
    anyio.run(_test_list_crashes_empty)


async def _test_list_crashes_empty() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/crashes", token=token)
        assert status == 200
        assert data == []


def test_list_crashes_returns_seeded_summary() -> None:
    anyio.run(_test_list_crashes_seeded)


async def _test_list_crashes_seeded() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    _seed_crash(audit_engine)
    token = _access_token()
    async with _lifespan(app):
        status, data = await _http(app, "GET", "/admin/crashes", token=token)
        assert status == 200
        assert len(data) == 1
        assert data[0]["player_id"] == "player-1"
        assert data[0]["command_text"] == "go north"
        # List view is a summary — stack_trace is only on the detail endpoint.
        assert "stack_trace" not in data[0]


def test_get_crash_returns_full_detail() -> None:
    anyio.run(_test_get_crash_detail)


async def _test_get_crash_detail() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    _seed_crash(audit_engine)
    token = _access_token()
    async with _lifespan(app):
        status, listed = await _http(app, "GET", "/admin/crashes", token=token)
        crash_id = listed[0]["id"]
        status, data = await _http(
            app, "GET", f"/admin/crashes/{crash_id}", token=token
        )
        assert status == 200
        assert "RuntimeError: boom" in data["stack_trace"]


def test_get_crash_returns_404_for_unknown_id() -> None:
    anyio.run(_test_get_crash_unknown)


async def _test_get_crash_unknown() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, _data = await _http(app, "GET", "/admin/crashes/999999", token=token)
        assert status == 404


def test_crashes_endpoint_requires_auth() -> None:
    anyio.run(_test_crashes_requires_auth)


async def _test_crashes_requires_auth() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, _data = await _http(app, "GET", "/admin/crashes")
        assert status in (401, 403)
