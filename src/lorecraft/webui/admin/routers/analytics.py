"""Admin API router for analytics queries (Sprint 10.5 foundation, no dashboard yet)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlmodel import Session

from lorecraft.webui.admin.auth import Observer
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
    quest_completion_funnel,
    top_commands,
)

router = APIRouter(prefix="/analytics", tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


def _since(range_str: str) -> float:
    try:
        duration = parse_range(range_str)
    except InvalidRangeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return time.time() - duration


@router.get("/commands")
async def analytics_commands(
    request: Request, _: Observer, range: str = "24h", top: int = 20
) -> list[dict[str, Any]]:
    state = _state(request)
    since = _since(range)
    with Session(state.audit_engine) as session:
        return top_commands(session, since=since, limit=top)


@router.get("/npcs")
async def analytics_npcs(
    request: Request, _: Observer, range: str = "7d", npc: str | None = None
) -> list[dict[str, Any]]:
    state = _state(request)
    since = _since(range)
    with Session(state.audit_engine) as session:
        return npc_interaction_counts(session, since=since, npc_id=npc)


@router.get("/quests")
async def analytics_quests(
    request: Request, _: Observer, range: str = "7d"
) -> list[dict[str, Any]]:
    state = _state(request)
    since = _since(range)
    with Session(state.audit_engine) as session:
        return quest_completion_counts(session, since=since)


@router.get("/quest-funnel")
async def analytics_quest_funnel(
    request: Request, _: Observer, range: str = "7d"
) -> list[dict[str, Any]]:
    """Per-quest started/completed/failed counts (Sprint 51), sourced from
    live `PlayerQuestProgress` rows rather than the (currently unpopulated)
    audit log — see `quest_completion_funnel`'s docstring."""
    state = _state(request)
    since = _since(range)
    with Session(state.game_engine) as session:
        return quest_completion_funnel(session, since=since)


@router.get("/player-hours")
async def analytics_player_hours(
    request: Request, _: Observer, range: str = "7d"
) -> list[dict[str, Any]]:
    state = _state(request)
    since = _since(range)
    with Session(state.game_engine) as session:
        return player_hours(session, since=since)


@router.get("/latency")
async def analytics_latency(
    request: Request, _: Observer, range: str = "24h"
) -> dict[str, float]:
    state = _state(request)
    since = _since(range)
    with Session(state.audit_engine) as session:
        return command_latency_percentiles(session, since=since)


@router.get("/performance")
async def analytics_performance(
    request: Request, _: Observer, range: str = "24h"
) -> dict[str, dict[str, float]]:
    """p50/p95/p99 by operation (command_parse / condition_evaluate / db_commit
    / command_handler) from COMMAND_EXECUTED perf payloads (Sprint 35.3)."""
    state = _state(request)
    since = _since(range)
    with Session(state.audit_engine) as session:
        return operation_latency_percentiles(session, since=since)


@router.get("/dashboard")
async def analytics_dashboard(
    request: Request,
    _: Observer,
    range: str = "24h",
    timeline_limit: int = 100,
    commands_limit: int = 10,
) -> dict[str, Any]:
    """One-call analytics dashboard payload backing the admin console's
    Analytics tab. Sprint 49: p50/p95/p99 latency by operation, the recent
    operation timeline, and the activity-by-hour heatmap. Sprint 51 adds
    three more widget payloads (`top_commands`, `npc_interactions`,
    `quest_funnel`) — each is an independent key computed from its own
    analytics function, so any one widget can be dropped from the frontend
    (or this key removed here) without touching the others."""
    state = _state(request)
    since = _since(range)
    timeline_limit = max(1, min(timeline_limit, 500))
    commands_limit = max(1, min(commands_limit, 50))
    with Session(state.audit_engine) as session:
        payload: dict[str, Any] = {
            "range": range,
            "latency_by_operation": operation_latency_percentiles(session, since=since),
            "timeline": operation_timeline(session, limit=timeline_limit),
            "heatmap": activity_by_hour(session, since=since),
            "top_commands": top_commands(session, since=since, limit=commands_limit),
            "npc_interactions": npc_interaction_counts(session, since=since),
        }
    with Session(state.game_engine) as game_session:
        payload["quest_funnel"] = quest_completion_funnel(game_session, since=since)
    return payload
