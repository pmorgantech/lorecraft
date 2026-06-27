"""Synchronous in-process event bus."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable


class GameEvent(StrEnum):
    ITEM_TAKEN = "item_taken"
    ITEM_DROPPED = "item_dropped"
    ITEM_USED = "item_used"
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
    QUEST_UPDATED = "quest_updated"
    QUEST_COMPLETED = "quest_completed"
    TIME_ADVANCED = "time_advanced"
    HOUR_CHANGED = "hour_changed"
    DAY_CHANGED = "day_changed"
    SEASON_CHANGED = "season_changed"
    WEATHER_CHANGED = "weather_changed"
    TRADE_COMPLETED = "trade_completed"
    PLAYER_DISCONNECTED = "player_disconnected"
    PLAYER_RECONNECTED = "player_reconnected"
    WORLD_CHANGESET_PROMOTED = "world_changeset_promoted"
    SAVE_LOADED = "save_loaded"
    COMBAT_TICK_DUE = "combat_tick_due"
    NPC_MOVE_DUE = "npc_move_due"
    SCHEDULED_JOB_DUE = "scheduled_job_due"
    GRACE_PERIOD_EXPIRED = "grace_period_expired"


WORK_EVENTS = {
    GameEvent.COMBAT_TICK_DUE,
    GameEvent.NPC_MOVE_DUE,
    GameEvent.SCHEDULED_JOB_DUE,
    GameEvent.GRACE_PERIOD_EXPIRED,
}


@dataclass(frozen=True)
class Event:
    type: GameEvent
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HandlerResult:
    handler_name: str
    value: Any = None
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


EventHandler = Callable[[Event, Any], Any]


@dataclass(frozen=True)
class _RegisteredHandler:
    priority: int
    handler: EventHandler


class EventBus:
    """Simple synchronous bus with priority ordering and exception isolation."""

    def __init__(self) -> None:
        self._handlers: dict[GameEvent, list[_RegisteredHandler]] = defaultdict(list)

    def on(self, event_type: GameEvent, handler: EventHandler, *, priority: int = 0) -> None:
        handlers = self._handlers[event_type]
        handlers.append(_RegisteredHandler(priority=priority, handler=handler))
        handlers.sort(key=lambda registered: registered.priority, reverse=True)

    def emit(self, event: Event, ctx: Any) -> list[HandlerResult]:
        results: list[HandlerResult] = []
        for registered in self._handlers.get(event.type, []):
            try:
                value = registered.handler(event, ctx)
                results.append(HandlerResult(_handler_name(registered.handler), value=value))
            except Exception as exc:
                results.append(HandlerResult(_handler_name(registered.handler), error=exc))
        return results

    def is_work_event(self, event_type: GameEvent) -> bool:
        return event_type in WORK_EVENTS


def _handler_name(handler: EventHandler) -> str:
    return getattr(handler, "__name__", handler.__class__.__name__)
