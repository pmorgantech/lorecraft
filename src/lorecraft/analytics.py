"""Analytics query functions over the audit log and player sessions.

Sprint 10.5 foundation: query functions only, computed from data the engine
already records (the audit log, player sessions) — no dashboard, no new
instrumentation. Metrics that need dedicated instrumentation (command
latency percentiles, event bus queue depth) are deferred to Sprint 13 and
intentionally not exposed here.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from typing import Any

from sqlmodel import Session, col, select

from lorecraft.game.events import GameEvent
from lorecraft.models.audit import AuditEvent
from lorecraft.models.session import PlayerSession
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
