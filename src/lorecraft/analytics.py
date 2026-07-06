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
from lorecraft.features.quests.models import PlayerQuestProgress
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


def quest_completion_funnel(
    game_session: Session, *, since: float
) -> list[dict[str, Any]]:
    """Per-quest started/completed/failed/in-progress counts (Sprint 51).

    Sourced from live `PlayerQuestProgress` rows in the **game** DB, not the
    audit log — unlike `quest_completion_counts` above, whose event types
    (`QUEST_UPDATED`/`QUEST_COMPLETED`/`QUEST_FAILED`) are only ever queued on
    the in-process event bus and never persisted as `AuditEvent` rows, so
    that query is always empty against real data. `started_at`/`completed_at`
    are real epoch seconds (same clock as `AuditEvent.real_time`), so `since`
    windows the same way. Sorted by `started` descending.
    """
    stmt = select(PlayerQuestProgress).where(
        col(PlayerQuestProgress.started_at) >= since
    )
    per_quest: dict[str, dict[str, int]] = {}
    for progress in game_session.exec(stmt).all():
        bucket = per_quest.setdefault(
            progress.quest_id,
            {"started": 0, "completed": 0, "failed": 0, "in_progress": 0},
        )
        bucket["started"] += 1
        if progress.status == "completed":
            bucket["completed"] += 1
        elif progress.status == "failed":
            bucket["failed"] += 1
        else:
            bucket["in_progress"] += 1
    ranked = sorted(per_quest.items(), key=lambda kv: kv[1]["started"], reverse=True)
    return [{"quest_id": quest_id, **counts} for quest_id, counts in ranked]


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


def operation_latency_percentiles(
    session: Session, *, since: float
) -> dict[str, dict[str, float]]:
    """p50/p95/p99 latency (ms) **per named operation** since `since`.

    Extends `command_latency_percentiles` from a single aggregate to a
    per-operation view. Reads the `perf` breakdown that
    `CommandEngine._record_success` stamps on `COMMAND_EXECUTED` payloads —
    `command_parse` / `condition_evaluate` / `db_commit` (Sprint 35.2/35.3
    instrumentation) — plus the top-level command-handler `duration_ms`,
    surfaced as the `command_handler` operation so the existing metric is
    included. Events without a `perf` field (pre-35.3) still contribute their
    `command_handler` timing. Returns `{operation: {p50, p95, p99, count}}`,
    empty if no matching events.

    scheduler_tick / broadcast_send are timed too (35.2) but happen outside the
    per-command audit path, so they surface only in structured logs, not here.
    """
    stmt = select(AuditEvent).where(
        AuditEvent.event_type == GameEvent.COMMAND_EXECUTED.value,
        col(AuditEvent.real_time) >= since,
    )
    per_operation: dict[str, list[float]] = {}
    for event in session.exec(stmt).all():
        payload = event.payload_json
        handler = payload.get("duration_ms")
        if isinstance(handler, (int, float)):
            per_operation.setdefault("command_handler", []).append(float(handler))
        perf = payload.get("perf")
        if isinstance(perf, dict):
            for name, value in perf.items():
                if isinstance(value, (int, float)):
                    per_operation.setdefault(name, []).append(float(value))
    result: dict[str, dict[str, float]] = {}
    for name, values in per_operation.items():
        values.sort()
        result[name] = {
            "p50": _percentile(values, 0.50),
            "p95": _percentile(values, 0.95),
            "p99": _percentile(values, 0.99),
            "count": len(values),
        }
    return result


def operation_timeline(session: Session, *, limit: int = 100) -> list[dict[str, Any]]:
    """The most recent executed commands with their handler latency (Sprint 49).

    Newest first: `real_time`, `verb`, `actor_id`, `room_id`, `duration_ms`
    from `COMMAND_EXECUTED` payloads — the raw feed the dashboard renders as an
    operation timeline. `duration_ms` is `None` for pre-Sprint-13 events."""
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.event_type == GameEvent.COMMAND_EXECUTED.value)
        .order_by(col(AuditEvent.real_time).desc())
        .limit(limit)
    )
    timeline: list[dict[str, Any]] = []
    for event in session.exec(stmt).all():
        duration = event.payload_json.get("duration_ms")
        timeline.append(
            {
                "real_time": event.real_time,
                "verb": event.payload_json.get("verb"),
                "actor_id": event.actor_id,
                "room_id": event.room_id,
                "duration_ms": float(duration)
                if isinstance(duration, (int, float))
                else None,
            }
        )
    return timeline


def activity_by_hour(session: Session, *, since: float) -> list[dict[str, int]]:
    """Command activity bucketed by clock hour (UTC 0–23) since `since` (Sprint 49).

    A 24-bucket histogram — the player-activity heatmap the dashboard renders.
    Every hour 0–23 is present (count 0 when idle) so the heatmap is dense."""
    buckets: Counter[int] = Counter()
    stmt = select(AuditEvent).where(
        AuditEvent.event_type == GameEvent.COMMAND_EXECUTED.value,
        col(AuditEvent.real_time) >= since,
    )
    for event in session.exec(stmt).all():
        buckets[time.gmtime(event.real_time).tm_hour] += 1
    return [{"hour": hour, "count": buckets.get(hour, 0)} for hour in range(24)]


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
