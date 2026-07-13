"""Per-command gameplay context."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlmodel import Session

from lorecraft.engine.game.channels import (
    SAY_CHANNEL,
    ChatMessage,
    ChatScope,
)
from lorecraft.engine.game.channels import (
    get_registry as get_channel_registry,
)
from lorecraft.engine.game.connection_manager import ConnectionManagerProtocol
from lorecraft.engine.game.events import Event, EventBus, GameEvent, HandlerResult
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.message_types import Message, MessageType
from lorecraft.engine.game.parser import ParsedCommand
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room, WorldClock
from lorecraft.engine.repos.audit_repo import AuditRepo
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.types import JsonObject, JsonValue

# lorecraft.services imports lorecraft.engine.game.context (services/audit.py et al.), so a
# module-level import of lorecraft.engine.services.item_location here would be circular via
# services/__init__.py. TYPE_CHECKING-only import for the annotation (deferred by
# `from __future__ import annotations`); build_game_context() imports it for real.
if TYPE_CHECKING:
    from lorecraft.engine.services.effects import EffectService
    from lorecraft.engine.services.item_location import ItemLocationService
    from lorecraft.engine.services.ledger import LedgerService
    from lorecraft.engine.services.meters import MeterService


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
    manager: ConnectionManagerProtocol
    bus: EventBus
    audit: AuditRepo | None
    transaction: TransactionContext
    session_id: str
    rng: GameRng
    commit_state: Callable[[], None] | None = None
    commit_audit: Callable[[], None] | None = None
    rollback_state: Callable[[], None] | None = None
    messages: list[Message] = field(default_factory=list)
    room_messages: list[str] = field(default_factory=list)
    arrival_messages: list[str] = field(default_factory=list)
    # Chat (Sprint 45 split, Sprint 52 channels): `chat_echoes` is the actor's
    # own rendering (delivered on their command result); `chat_outbox` is
    # everything bound for other players, routed by each entry's scope in
    # `broadcast_command_effects`.
    chat_echoes: list[ChatMessage] = field(default_factory=list)
    chat_outbox: list[ChatMessage] = field(default_factory=list)
    updates: JsonObject = field(default_factory=dict)
    pending_events: list[Event] = field(default_factory=list)
    # Transient: the payload of the event a trigger is currently firing on (scripting engine
    # A4), so an effect can read event-specific data (e.g. the item just stored in a container).
    # Empty outside trigger execution; set by TriggerService before each `do` runs.
    event_payload: JsonObject = field(default_factory=dict)
    parsed_command: ParsedCommand | None = None
    # Deferred async WS deliveries produced by *synchronous* handlers that need
    # to push to another player's socket (e.g. Sprint 47 follow moving a
    # follower). Each entry is a zero-arg coroutine factory; the async command
    # loop drains them via `broadcast_command_effects` after handle_command
    # returns, since the event bus itself is synchronous and can't await.
    pending_deliveries: list[Callable[[], Awaitable[None]]] = field(
        default_factory=list
    )

    def defer_delivery(self, factory: Callable[[], Awaitable[None]]) -> None:
        """Queue a coroutine factory to be awaited in the async command loop.

        Lets a sync event handler schedule a WS push to another player without
        an event loop of its own; drained (exception-isolated) by
        `broadcast_command_effects`."""
        self.pending_deliveries.append(factory)

    def say(self, text: str, msg_type: MessageType = MessageType.SYSTEM) -> None:
        self.messages.append(Message(text, msg_type))

    def tell_room(self, text: str) -> None:
        """Narrate to the room the actor is leaving (or the current room, if
        the command doesn't move them) — see `tell_arrival` for the opposite
        case of narrating to the room the actor is entering."""
        self.room_messages.append(text)

    def _channel_scope(self, channel_id: str) -> ChatScope:
        """Resolve a channel's delivery scope from the registry. Unknown
        channels fall back to P2ROOM — the narrowest broadcast scope, so a
        typo'd channel can never accidentally go global."""
        channel = get_channel_registry().get(channel_id)
        return channel.scope if channel is not None else ChatScope.P2ROOM

    def chat_echo(self, channel_id: str, text: str) -> None:
        """The actor's own rendering of their chat (e.g. 'You say: "hi"') —
        delivered on their command result, tagged with the channel so clients
        can route/style it (chat pane, per-channel color)."""
        self.chat_echoes.append(
            ChatMessage(
                channel=channel_id, scope=self._channel_scope(channel_id), text=text
            )
        )

    def chat_out(
        self, channel_id: str, text: str, *, target_player_id: str | None = None
    ) -> None:
        """Chat bound for other players, routed by the channel's scope in
        `broadcast_command_effects` (Sprint 52.3): P2ROOM → the actor's room,
        P2ALL → everyone online (respecting subscriptions), P2P → exactly
        `target_player_id`."""
        self.chat_outbox.append(
            ChatMessage(
                channel=channel_id,
                scope=self._channel_scope(channel_id),
                text=text,
                target_player_id=target_player_id,
            )
        )

    def say_chat(self, text: str) -> None:
        """The actor's own echo on the `say` channel (Sprint 45 wrapper —
        kept separate from `say`'s narrative `messages` so clients can route
        conversation to its own pane)."""
        self.chat_echo(SAY_CHANNEL, text)

    def tell_room_chat(self, text: str) -> None:
        """`say`-channel chat heard by the rest of the room (Sprint 45
        wrapper) — broadcast as `message_type: "chat"`, never `room_event`."""
        self.chat_out(SAY_CHANNEL, text)

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
        """Return room items and NPCs as (id, name, aliases) for parser resolution.

        Uses the name_index column projection rather than materializing full Item
        rows: parser resolution only reads name+aliases, and full-row
        materialization was the dominant parse cost at scale (roadmap 36.2).
        """
        stacks = self.stack_repo.stacks_at(Location("room", self.room.id))
        names = self.item_repo.name_index(stack.item_id for stack in stacks)
        entities: list[tuple[str, str, list[str]]] = []
        for stack in stacks:
            entry = names.get(stack.item_id)
            if entry is not None:
                name, aliases = entry
                entities.append((stack.item_id, name, aliases))
        for npc in self.npc_repo.in_room(self.room.id):
            entities.append((npc.id, npc.name, [npc.name.lower()]))
        return entities

    def get_inventory(self) -> list[tuple[str, str, list[str]]]:
        """Return carried items as (id, name, aliases) for parser resolution.

        Projects name+aliases via name_index instead of materializing full Item
        rows — see get_visible_entities.
        """
        stacks = self.stack_repo.stacks_for_owner("player", self.player.id)
        names = self.item_repo.name_index(stack.item_id for stack in stacks)
        inventory: list[tuple[str, str, list[str]]] = []
        seen: set[str] = set()
        for stack in stacks:
            if stack.item_id in seen:
                continue
            entry = names.get(stack.item_id)
            if entry is not None:
                seen.add(stack.item_id)
                name, aliases = entry
                inventory.append((stack.item_id, name, aliases))
        return inventory


def build_game_context(
    session: Session,
    player: Player,
    room: Room,
    *,
    bus: EventBus,
    manager: ConnectionManagerProtocol,
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
    from lorecraft.engine.services.item_location import ItemLocationService
    from lorecraft.engine.services.ledger import LedgerService

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
