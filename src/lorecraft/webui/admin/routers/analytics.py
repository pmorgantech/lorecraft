"""Admin API router for analytics queries (Sprint 10.5 foundation, no dashboard yet)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlmodel import Session

from lorecraft.webui.admin.auth import Observer
from lorecraft.analytics import (
    InvalidRangeError,
    command_latency_percentiles,
    npc_interaction_counts,
    operation_latency_percentiles,
    parse_range,
    player_hours,
    quest_completion_counts,
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
