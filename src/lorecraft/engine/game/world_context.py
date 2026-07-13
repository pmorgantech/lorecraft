"""Actor-less execution context — the world surface a script can touch without a player.

`docs/scripting_engine_design.md` §3.1. Autonomous behavior (an NPC's agency loop, a weather
front, a scheduled trigger) has to read and mutate world state, emit events, roll the seedable
RNG, and narrate to rooms — but there is **no acting player**. `WorldContext` names exactly that
surface; :class:`GameContext` already provides all of it (it *is* a `WorldContext` plus a
player/room actor), so player-driven and autonomous code share one vocabulary.

Realized structurally (a :class:`typing.Protocol`) rather than as a dataclass base of
`GameContext`: the god-node `GameContext` is constructed by keyword in ~45 places and reworking
it into a nominal base risks the whole command path for no functional gain. A Protocol gives the
same guarantee — code typed against `WorldContext` *cannot* reach `.player` — with zero churn on
`GameContext`. The concrete actor-less implementation is :class:`StandaloneWorldContext`, built
by :func:`build_world_context`.

Tier 1. `GameContext` does not import this module; the arrow is one-way.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from sqlmodel import Session

from lorecraft.engine.game.connection_manager import ConnectionManagerProtocol
from lorecraft.engine.game.events import Event, EventBus, GameEvent, HandlerResult
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.world import WorldClock
from lorecraft.engine.repos.audit_repo import AuditRepo
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.types import JsonObject, JsonValue

if TYPE_CHECKING:
    from lorecraft.engine.services.effects import EffectService
    from lorecraft.engine.services.item_location import ItemLocationService
    from lorecraft.engine.services.ledger import LedgerService
    from lorecraft.engine.services.meters import MeterService

log = logging.getLogger(__name__)


def broadcast_room_async(
    manager: ConnectionManagerProtocol, room_id: str | None, text: str
) -> None:
    """Fire-and-forget room narration for an *autonomous* (non-command) event.

    There is no command loop to flush buffered narration through, so — exactly like
    ``transit.service._narrate`` — schedule the broadcast on the running loop and no-op when
    there isn't one (unit tests / scheduler-only contexts). Best-effort by design: a dropped
    narration never breaks the state change that triggered it.
    """
    if not room_id:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.create_task(
        manager.broadcast_to_room(
            room_id,
            {
                "type": "feed_append",
                "content": text,
                "message_type": MessageType.ROOM_EVENT.value,
            },
        )
    )


class WorldContext(Protocol):
    """The world surface shared by player-driven (`GameContext`) and autonomous execution.

    Everything here is actor-independent. A handler typed against ``WorldContext`` provably
    can't assume a player — which is the discipline that lets the same effect run from a command
    *and* from a weather tick. See ``docs/scripting_engine_design.md`` §3.1.
    """

    session: Session
    player_repo: PlayerRepo
    room_repo: RoomRepo
    item_repo: ItemRepo
    stack_repo: StackRepo
    npc_repo: NpcRepo
    item_location: ItemLocationService
    ledger: LedgerService
    meters: MeterService
    effects: EffectService
    manager: ConnectionManagerProtocol
    bus: EventBus
    audit: AuditRepo | None
    transaction: TransactionContext
    session_id: str
    rng: GameRng
    clock: WorldClock | None
    updates: JsonObject
    pending_events: list[Event]

    def emit(self, event: GameEvent, **payload: JsonValue) -> list[HandlerResult]: ...

    def queue_event(self, event: GameEvent, **payload: JsonValue) -> None: ...

    def flush_events(self) -> list[HandlerResult]: ...

    def push_update(self, key: str, value: JsonValue) -> None: ...


@dataclass
class StandaloneWorldContext:
    """Concrete actor-less :class:`WorldContext` for autonomous behavior.

    Built by :func:`build_world_context`. Unlike `GameContext`, room narration broadcasts
    immediately (there's no command result to piggyback on); event emission, the RNG, and the
    world clock behave identically so a scripted effect can't tell which context it's running in.
    """

    session: Session
    player_repo: PlayerRepo
    room_repo: RoomRepo
    item_repo: ItemRepo
    stack_repo: StackRepo
    npc_repo: NpcRepo
    item_location: ItemLocationService
    ledger: LedgerService
    meters: MeterService
    effects: EffectService
    manager: ConnectionManagerProtocol
    bus: EventBus
    audit: AuditRepo | None
    transaction: TransactionContext
    session_id: str
    rng: GameRng
    clock: WorldClock | None
    updates: JsonObject = field(default_factory=dict)
    pending_events: list[Event] = field(default_factory=list)

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

    def push_update(self, key: str, value: JsonValue) -> None:
        self.updates[key] = value

    def narrate_room(self, room_id: str | None, text: str) -> None:
        broadcast_room_async(self.manager, room_id, text)


def build_world_context(
    session: Session,
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
) -> StandaloneWorldContext:
    """Factory for :class:`StandaloneWorldContext` — the actor-less peer of
    :func:`~lorecraft.engine.game.context.build_game_context`.

    Wires the same repos/services from ``session`` but takes no player or room. Autonomous
    callers (the trigger service on a `tick`, a weather controller, an NPC agency loop) build one
    of these to run world-safe conditions/effects. ``clock`` is passed straight through — a
    ``None`` clock is legitimate for a world without a seeded clock row, never synthesized.
    """
    from lorecraft.engine.services.item_location import ItemLocationService
    from lorecraft.engine.services.ledger import LedgerService

    stack_repo = StackRepo(session)
    item_repo = ItemRepo(session)
    return StandaloneWorldContext(
        session=session,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=item_repo,
        stack_repo=stack_repo,
        npc_repo=NpcRepo(session),
        item_location=ItemLocationService(
            session, stack_repo=stack_repo, item_repo=item_repo
        ),
        ledger=LedgerService(),
        meters=meters,
        effects=effects,
        manager=manager,
        bus=bus,
        audit=AuditRepo(audit_session) if audit_session is not None else None,
        transaction=transaction,
        session_id=session_id,
        rng=rng,
        clock=clock,
    )


# Static guarantee that `GameContext` satisfies the `WorldContext` surface (the whole point of
# the structural realization). If a future edit to `GameContext` drops or retypes a shared
# member, this line fails the type check — a compile-time canary, no runtime cost.
if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext

    def _game_context_is_a_world_context(ctx: GameContext) -> WorldContext:
        return ctx
