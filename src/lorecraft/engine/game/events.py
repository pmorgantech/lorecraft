"""Synchronous in-process event bus."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from lorecraft.observability import record_span
from lorecraft.types import JsonObject

log = logging.getLogger(__name__)


class GameEvent(StrEnum):
    COMMAND_EXECUTED = "command_executed"
    COMMAND_BLOCKED = "command_blocked"
    COMMAND_FAILED = "command_failed"
    ITEM_TAKEN = "item_taken"
    ITEM_DROPPED = "item_dropped"
    ITEM_USED = "item_used"
    ITEM_GIVEN = "item_given"
    ITEM_STORED = "item_stored"  # a carried item placed into a container (A4)
    ITEM_REMOVED = "item_removed"  # an item taken out of a container (A4)
    PLAYER_MOVED = "player_moved"
    PLAYER_DIED = "player_died"
    PLAYER_RESPAWNED = "player_respawned"
    NPC_MOVED = "npc_moved"
    NPC_DIED = "npc_died"
    NPC_FLED = "npc_fled"
    COMBAT_STARTED = "combat_started"
    COMBAT_ENDED = "combat_ended"
    PLAYER_ATTACKED = "player_attacked"
    NPC_ATTACKED = "npc_attacked"
    SKILL_IMPROVED = "skill_improved"
    PLAYER_LEVELED_UP = "player_leveled_up"
    QUEST_UPDATED = "quest_updated"
    QUEST_COMPLETED = "quest_completed"
    QUEST_FAILED = "quest_failed"
    TIME_ADVANCED = "time_advanced"
    HOUR_CHANGED = "hour_changed"
    DAY_CHANGED = "day_changed"
    SEASON_CHANGED = "season_changed"
    WEATHER_CHANGED = "weather_changed"
    MOON_PHASE_CHANGED = "moon_phase_changed"
    TIDE_CHANGED = "tide_changed"
    TRADE_COMPLETED = "trade_completed"
    PLAYER_DISCONNECTED = "player_disconnected"
    PLAYER_RECONNECTED = "player_reconnected"
    WORLD_CHANGESET_PROMOTED = "world_changeset_promoted"
    ENGINE_RESTART_REQUESTED = "engine_restart_requested"
    SAVE_LOADED = "save_loaded"
    COMBAT_TICK_DUE = "combat_tick_due"
    NPC_MOVE_DUE = "npc_move_due"
    SCHEDULED_JOB_DUE = "scheduled_job_due"
    GRACE_PERIOD_EXPIRED = "grace_period_expired"
    METER_DEPLETED = "meter_depleted"
    METER_RECOVERED = "meter_recovered"
    EFFECT_APPLIED = "effect_applied"
    EFFECT_EXPIRED = "effect_expired"
    EFFECT_REMOVED = "effect_removed"
    ITEM_EQUIPPED = "item_equipped"
    ITEM_UNEQUIPPED = "item_unequipped"
    ITEM_PURCHASED = "item_purchased"
    ITEM_SOLD = "item_sold"
    MONEY_DEPOSITED = "money_deposited"
    MONEY_WITHDRAWN = "money_withdrawn"
    TRANSIT_DEPARTED = "transit_departed"
    TRANSIT_ARRIVED = "transit_arrived"
    TRANSIT_BOARDED = "transit_boarded"
    TRANSIT_DISEMBARKED = "transit_disembarked"
    ISSUE_FILED = "issue_filed"


WORK_EVENTS = {
    GameEvent.COMBAT_TICK_DUE,
    GameEvent.NPC_MOVE_DUE,
    GameEvent.SCHEDULED_JOB_DUE,
    GameEvent.GRACE_PERIOD_EXPIRED,
}


@dataclass(frozen=True)
class Event:
    type: GameEvent
    payload: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class HandlerResult:
    handler_name: str
    value: object = None
    error: Exception | None = None
    duration_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None


class EventHandler(Protocol):
    def __call__(self, event: Event, ctx: object) -> object: ...


@dataclass(frozen=True)
class _RegisteredHandler:
    priority: int
    handler: EventHandler


class EventBus:
    """Simple synchronous bus with priority ordering and exception isolation."""

    def __init__(self) -> None:
        self._handlers: dict[GameEvent, list[_RegisteredHandler]] = defaultdict(list)

    def on(
        self, event_type: GameEvent, handler: EventHandler, *, priority: int = 0
    ) -> None:
        handlers = self._handlers[event_type]
        handlers.append(_RegisteredHandler(priority=priority, handler=handler))
        handlers.sort(key=lambda registered: registered.priority, reverse=True)

    def emit(self, event: Event, ctx: object) -> list[HandlerResult]:
        handlers = self._handlers.get(event.type, [])
        results: list[HandlerResult] = []
        for registered in handlers:
            handler_name = _handler_name(registered.handler)
            start = time.perf_counter()
            try:
                value = registered.handler(event, ctx)
                duration_ms = (time.perf_counter() - start) * 1000
                results.append(
                    HandlerResult(handler_name, value=value, duration_ms=duration_ms)
                )
            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                results.append(
                    HandlerResult(handler_name, error=exc, duration_ms=duration_ms)
                )
            log.debug(
                "event_handler event=%s handler=%s duration_ms=%.3f depth=%d",
                event.type.value,
                handler_name,
                duration_ms,
                len(handlers),
            )
            # Sprint 57.1: feed the same per-command trace buffer
            # time_operation() writes to, so a command's trace includes the
            # event handlers it triggered, not just parse/condition/commit.
            record_span(f"event:{event.type.value}:{handler_name}", duration_ms)
        return results

    def is_work_event(self, event_type: GameEvent) -> bool:
        return event_type in WORK_EVENTS

    def handler_count(self, event_type: GameEvent) -> int:
        return len(self._handlers.get(event_type, ()))


def _handler_name(handler: EventHandler) -> str:
    return getattr(handler, "__name__", handler.__class__.__name__)
