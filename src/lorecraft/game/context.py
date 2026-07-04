"""Per-command gameplay context."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlmodel import Session

from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.events import Event, EventBus, GameEvent, HandlerResult
from lorecraft.game.parser import ParsedCommand
from lorecraft.game.rng import GameRng
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player
from lorecraft.models.world import Room, WorldClock
from lorecraft.repos.audit_repo import AuditRepo
from lorecraft.repos.dialogue_repo import DialogueRepo
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.news_repo import NewsRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.quest_repo import QuestRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.types import JsonObject, JsonValue

# lorecraft.services imports lorecraft.game.context (services/audit.py et al.), so a
# module-level import of lorecraft.services.item_location here would be circular via
# services/__init__.py. TYPE_CHECKING-only import for the annotation (deferred by
# `from __future__ import annotations`); build_game_context() imports it for real.
if TYPE_CHECKING:
    from lorecraft.services.effects import EffectService
    from lorecraft.services.item_location import ItemLocationService
    from lorecraft.services.ledger import LedgerService
    from lorecraft.services.meters import MeterService


@dataclass
class GameContext:
    player: Player
    room: Room
    clock: WorldClock | None
    session: Session
    player_repo: PlayerRepo
    room_repo: RoomRepo
    item_repo: ItemRepo
    stack_repo: StackRepo
    item_location: ItemLocationService
    ledger: LedgerService
    meters: MeterService
    effects: EffectService
    npc_repo: NpcRepo
    manager: ConnectionManager
    bus: EventBus
    audit: AuditRepo | None
    transaction: TransactionContext
    session_id: str
    rng: GameRng
    commit_state: Callable[[], None] | None = None
    commit_audit: Callable[[], None] | None = None
    rollback_state: Callable[[], None] | None = None
    quest_repo: QuestRepo | None = None
    dialogue_repo: DialogueRepo | None = None
    news_repo: NewsRepo | None = None
    messages: list[str] = field(default_factory=list)
    room_messages: list[str] = field(default_factory=list)
    arrival_messages: list[str] = field(default_factory=list)
    updates: JsonObject = field(default_factory=dict)
    pending_events: list[Event] = field(default_factory=list)
    parsed_command: ParsedCommand | None = None

    def say(self, text: str) -> None:
        self.messages.append(text)

    def tell_room(self, text: str) -> None:
        """Narrate to the room the actor is leaving (or the current room, if
        the command doesn't move them) — see `tell_arrival` for the opposite
        case of narrating to the room the actor is entering."""
        self.room_messages.append(text)

    def tell_arrival(self, text: str) -> None:
        """Narrate to the room the actor is entering (e.g. "X arrives from
        the east."). Only meaningful for commands that move the player —
        `broadcast_command_effects` always targets this at the post-command
        room, regardless of whether the room changed."""
        self.arrival_messages.append(text)

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

    def rollback_state_changes(self) -> None:
        if self.rollback_state is not None:
            self.rollback_state()

    def get_visible_entities(self) -> list[tuple[str, str, list[str]]]:
        """Return room items and NPCs as (id, name, aliases) for parser resolution."""
        entities: list[tuple[str, str, list[str]]] = []
        for _stack, item in self.item_repo.items_in_room(self.room.id):
            entities.append((item.id, item.name, list(item.aliases)))
        for npc in self.npc_repo.in_room(self.room.id):
            entities.append((npc.id, npc.name, [npc.name.lower()]))
        return entities

    def get_inventory(self) -> list[tuple[str, str, list[str]]]:
        """Return carried items as (id, name, aliases) for parser resolution."""
        inventory: list[tuple[str, str, list[str]]] = []
        seen: set[str] = set()
        for stack in self.stack_repo.stacks_for_owner("player", self.player.id):
            if stack.item_id in seen:
                continue
            item = self.item_repo.get(stack.item_id)
            if item is not None:
                seen.add(stack.item_id)
                inventory.append((item.id, item.name, list(item.aliases)))
        return inventory


def build_game_context(
    session: Session,
    player: Player,
    room: Room,
    *,
    bus: EventBus,
    manager: ConnectionManager,
    transaction: TransactionContext,
    session_id: str,
    rng: GameRng,
    meters: MeterService,
    effects: EffectService,
    clock: WorldClock | None = None,
    audit_session: Session | None = None,
    commit_state: Callable[[], None] | None = None,
    commit_audit: Callable[[], None] | None = None,
    rollback_state: Callable[[], None] | None = None,
) -> GameContext:
    """Factory for GameContext — wires all repos and services.

    Both real entry points (`main.py`'s `/ws` command loop, `web/frontend.py`'s
    `POST /command`) use this factory, so construction can't drift between
    them. `session` backs every game-state repo. Audit events use a separate
    DB/engine in production, so pass `audit_session` (its own `Session`) to
    also wire `audit`; omit it (as tests without an audit DB do) to leave
    `ctx.audit` as `None`.

    `clock` is passed straight through — callers pass `room_repo.world_clock()`,
    which is legitimately `None` if the world has no seeded clock row. This
    factory does not synthesize a fallback clock; a fabricated one would be
    silently wrong data, not a safe default.
    """
    from lorecraft.services.item_location import ItemLocationService
    from lorecraft.services.ledger import LedgerService

    stack_repo = StackRepo(session)
    item_repo = ItemRepo(session)
    return GameContext(
        player=player,
        room=room,
        clock=clock,
        session=session,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=item_repo,
        stack_repo=stack_repo,
        item_location=ItemLocationService(
            session, stack_repo=stack_repo, item_repo=item_repo
        ),
        ledger=LedgerService(),
        meters=meters,
        effects=effects,
        npc_repo=NpcRepo(session),
        quest_repo=QuestRepo(session),
        dialogue_repo=DialogueRepo(session),
        news_repo=NewsRepo(session),
        manager=manager,
        bus=bus,
        audit=AuditRepo(audit_session) if audit_session is not None else None,
        transaction=transaction,
        session_id=session_id,
        rng=rng,
        commit_state=commit_state,
        commit_audit=commit_audit,
        rollback_state=rollback_state,
    )
