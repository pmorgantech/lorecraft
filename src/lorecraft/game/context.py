"""Per-command gameplay context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lorecraft.game.events import Event, EventBus, GameEvent, HandlerResult
from lorecraft.game.transaction import TransactionContext


@dataclass
class GameContext:
    player: Any
    room: Any
    clock: Any
    player_repo: Any
    room_repo: Any
    item_repo: Any
    npc_repo: Any
    manager: Any
    bus: EventBus
    audit: Any
    transaction: TransactionContext
    session_id: str
    messages: list[str] = field(default_factory=list)
    room_messages: list[str] = field(default_factory=list)
    updates: dict[str, Any] = field(default_factory=dict)

    def say(self, text: str) -> None:
        self.messages.append(text)

    def tell_room(self, text: str) -> None:
        self.room_messages.append(text)

    def push_update(self, key: str, value: Any) -> None:
        self.updates[key] = value

    def emit(self, event: GameEvent, **payload: Any) -> list[HandlerResult]:
        return self.bus.emit(Event(event, payload), self)
