"""Per-command gameplay context."""

from __future__ import annotations

from dataclasses import dataclass, field

from lorecraft.game.events import Event, EventBus, GameEvent, HandlerResult
from lorecraft.game.transaction import TransactionContext
from lorecraft.types import JsonObject, JsonValue, PlayerState, RoomState


@dataclass
class GameContext:
    player: PlayerState
    room: RoomState
    clock: object
    player_repo: object | None
    room_repo: object | None
    item_repo: object | None
    npc_repo: object | None
    manager: object | None
    bus: EventBus
    audit: object | None
    transaction: TransactionContext
    session_id: str
    messages: list[str] = field(default_factory=list)
    room_messages: list[str] = field(default_factory=list)
    updates: JsonObject = field(default_factory=dict)

    def say(self, text: str) -> None:
        self.messages.append(text)

    def tell_room(self, text: str) -> None:
        self.room_messages.append(text)

    def push_update(self, key: str, value: JsonValue) -> None:
        self.updates[key] = value

    def emit(self, event: GameEvent, **payload: JsonValue) -> list[HandlerResult]:
        return self.bus.emit(Event(event, payload), self)
