"""Analytics query functions over the audit log and player sessions.

Sprint 10.5 foundation: query functions computed from data the engine already
records (the audit log, player sessions) — no dashboard. Sprint 13 added
`command_latency_percentiles`, sourced from the `duration_ms` field
`CommandEngine` now stamps onto every `COMMAND_EXECUTED` audit event payload
(see `game/engine.py`); event-handler timing itself lives only in structured
DEBUG logs (`game/events.py`'s `EventBus.emit`), not the audit log, so it has
no query function here.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from typing import Any

from sqlmodel import Session, col, select

from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.session import PlayerSession
from lorecraft.types import JsonValue

_RANGE_RE = re.compile(r"^(\d+)([hdwm])$")
_RANGE_SECONDS = {"h": 3600, "d": 86400, "w": 604800, "m": 60}


class InvalidRangeError(ValueError):
    """Raised when a `range` query parameter isn't in `<N><h|d|w|m>` form."""


def parse_range(range_str: str) -> float:
    """Parse a `range` query param like "24h", "7d", "2w" into a duration in seconds."""
    match = _RANGE_RE.match(range_str.strip().lower())
    if match is None:
        raise InvalidRangeError(
            f"Invalid range {range_str!r}; expected e.g. '24h', '7d', '2w', '30m'"
        )
    count, unit = match.groups()
    return int(count) * _RANGE_SECONDS[unit]


def top_commands(
    session: Session, *, since: float, limit: int = 20
) -> list[dict[str, Any]]:
    """Most frequently executed command verbs since `since` (epoch seconds)."""
    stmt = select(AuditEvent).where(
        AuditEvent.event_type == GameEvent.COMMAND_EXECUTED.value,
        col(AuditEvent.real_time) >= since,
    )
    counts: Counter[str] = Counter()
    for event in session.exec(stmt).all():
        verb = event.payload_json.get("verb")
        if isinstance(verb, str):
            counts[verb] += 1
    return [{"verb": verb, "count": count} for verb, count in counts.most_common(limit)]


def npc_interaction_counts(
    session: Session, *, since: float, npc_id: str | None = None
) -> list[dict[str, Any]]:
    """Count audit events targeting each NPC (attacks, dialogue, etc.) since `since`.

    Pass `npc_id` to scope to a single NPC's interaction count.
    """
    stmt = select(AuditEvent).where(
        col(AuditEvent.real_time) >= since, col(AuditEvent.target_id).is_not(None)
    )
    if npc_id is not None:
        stmt = stmt.where(AuditEvent.target_id == npc_id)
    counts: Counter[str] = Counter()
    for event in session.exec(stmt).all():
        if event.target_id is not None:
            counts[event.target_id] += 1
    return [
        {"npc_id": target_id, "interactions": count}
        for target_id, count in counts.most_common()
    ]


def quest_completion_counts(session: Session, *, since: float) -> list[dict[str, Any]]:
    """Count QUEST_COMPLETED audit events per quest id since `since`."""
    stmt = select(AuditEvent).where(
        AuditEvent.event_type == GameEvent.QUEST_COMPLETED.value,
        col(AuditEvent.real_time) >= since,
    )
    counts: Counter[str] = Counter()
    for event in session.exec(stmt).all():
        quest_id = event.payload_json.get("quest_id") or event.target_id
        if isinstance(quest_id, str):
            counts[quest_id] += 1
    return [
        {"quest_id": quest_id, "completions": count}
        for quest_id, count in counts.most_common()
    ]


def command_latency_percentiles(session: Session, *, since: float) -> dict[str, float]:
    """p50/p95/p99 command handler latency (ms) since `since`.

    Sourced from `duration_ms` on `COMMAND_EXECUTED` audit event payloads
    (stamped by `CommandEngine._record_success`). Older events recorded
    before Sprint 13 have no `duration_ms` and are excluded.
    """
    stmt = select(AuditEvent).where(
        AuditEvent.event_type == GameEvent.COMMAND_EXECUTED.value,
        col(AuditEvent.real_time) >= since,
    )
    durations = sorted(
        float(duration)
        for event in session.exec(stmt).all()
        if isinstance(duration := event.payload_json.get("duration_ms"), (int, float))
    )
    if not durations:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "count": 0}
    return {
        "p50": _percentile(durations, 0.50),
        "p95": _percentile(durations, 0.95),
        "p99": _percentile(durations, 0.99),
        "count": len(durations),
    }


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Nearest-rank percentile; `sorted_values` must be sorted ascending."""
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(len(sorted_values) * fraction))
    return round(sorted_values[index], 3)


def player_hours(
    game_session: Session, *, since: float, now: float | None = None
) -> list[dict[str, JsonValue]]:
    """Total connected hours per player from `PlayerSession` rows since `since`."""
    now = now if now is not None else time.time()
    stmt = select(PlayerSession).where(col(PlayerSession.connected_at) >= since)
    totals: dict[str, float] = {}
    for session_row in game_session.exec(stmt).all():
        ended_at = session_row.disconnected_at or now
        seconds = max(0.0, ended_at - session_row.connected_at)
        totals[session_row.player_id] = totals.get(session_row.player_id, 0.0) + seconds
    ranked = sorted(totals.items(), key=lambda pair: pair[1], reverse=True)
    return [
        {"player_id": player_id, "hours": round(seconds / 3600, 2)}
        for player_id, seconds in ranked
    ]
