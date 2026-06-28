"""Per-command gameplay context."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.events import Event, EventBus, GameEvent, HandlerResult
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player
from lorecraft.models.world import Room, WorldClock
from lorecraft.repos.audit_repo import AuditRepo
from lorecraft.repos.dialogue_repo import DialogueRepo
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.quest_repo import QuestRepo
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
    commit_state: Callable[[], None] | None = None
    commit_audit: Callable[[], None] | None = None
    quest_repo: QuestRepo | None = None
    dialogue_repo: DialogueRepo | None = None
    messages: list[str] = field(default_factory=list)
    room_messages: list[str] = field(default_factory=list)
    updates: JsonObject = field(default_factory=dict)
    pending_events: list[Event] = field(default_factory=list)

    def say(self, text: str) -> None:
        self.messages.append(text)

    def tell_room(self, text: str) -> None:
        self.room_messages.append(text)

    def push_update(self, key: str, value: JsonValue) -> None:
        self.updates[key] = value

    def emit(self, event: GameEvent, **payload: JsonValue) -> list[HandlerResult]:
        return self.bus.emit(Event(event, payload), self)

    def queue_event(self, event: GameEvent, **payload: JsonValue) -> None:
        self.pending_events.append(Event(event, payload))

    def flush_events(self) -> list[HandlerResult]:
        results: list[HandlerResult] = []
        for event in self.pending_events:
            results.extend(self.bus.emit(event, self))
        self.pending_events.clear()
        return results

    def commit_state_changes(self) -> None:
        if self.commit_state is not None:
            self.commit_state()

    def commit_audit_events(self) -> None:
        if self.commit_audit is not None:
            self.commit_audit()
