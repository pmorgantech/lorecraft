"""Per-command gameplay context."""

from __future__ import annotations

from dataclasses import dataclass, field

from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.events import Event, EventBus, GameEvent, HandlerResult
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player
from lorecraft.models.world import Room, WorldClock
from lorecraft.repos.audit_repo import AuditRepo
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.types import JsonObject, JsonValue


@dataclass
class GameContext:
    player: Player
    room: Room
    clock: WorldClock | None
    player_repo: PlayerRepo
    room_repo: RoomRepo
    item_repo: ItemRepo
    npc_repo: NpcRepo
    manager: ConnectionManager
    bus: EventBus
    audit: AuditRepo | None
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
