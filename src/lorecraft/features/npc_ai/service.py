"""Autonomous NPC behavior — the agency loop (`docs/scripting_engine_design.md` §3.2).

On each world tick, NPCs carrying an ``ai`` config can act on their own initiative. Movement
modes remain the first agency layer:

* ``wander`` — step to a random adjacency-valid exit (optionally confined to an ``area``), every
  ``move_every`` ticks, rolled through the seedable :class:`GameRng` so runs replay faithfully.
* ``patrol`` — walk a fixed ``route`` of room ids in order, looping.

Non-movement autonomy lives in ``ai.actions``: cadence-gated room-visible idle actions such as
``say``, ``emote``, and raw ``narrate`` lines. Moving and idle actions share the same Tier 2
service so NPC autonomy has one owner.

Each move updates ``NPC.current_room_id``, narrates depart/arrive to the rooms, and — the whole
point — **emits ``NPC_MOVED``**, which the :class:`~lorecraft.engine.scripting.triggers.TriggerService`
turns into an ``encounter`` for any player already standing in the destination. So "an NPC walks
up to you and reacts" now works, the mirror of the player-walks-into-NPC case.

Tier 2 feature ``npc_ai``. It builds an actor-less
:class:`~lorecraft.engine.game.world_context.StandaloneWorldContext` (A1) to run the tick, since
there is no player driving it.
"""

from __future__ import annotations

import logging

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.game.world_context import (
    StandaloneWorldContext,
    broadcast_room_async,
    build_world_context,
)
from lorecraft.engine.models.world import NPC, Room
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.types import JsonObject

log = logging.getLogger(__name__)

MODE_WANDER = "wander"
MODE_PATROL = "patrol"
ACTION_NARRATE = "narrate"
ACTION_SAY = "say"
ACTION_EMOTE = "emote"
ACTION_TYPES = {ACTION_NARRATE, ACTION_SAY, ACTION_EMOTE}


class NpcBehaviorService:
    """Ticks NPC agency modes on ``TIME_ADVANCED`` and emits ``NPC_MOVED``."""

    def __init__(
        self,
        game_engine: Engine,
        manager: ConnectionManager,
        rng: GameRng,
        meters: MeterService,
        effects: EffectService,
    ) -> None:
        self._engine = game_engine
        self._manager = manager
        self._rng = rng
        self._meters = meters
        self._effects = effects
        self._bus: EventBus | None = None
        # Per-NPC tick counter (in-memory): move only every `move_every` ticks.
        self._ticks: dict[str, int] = {}
        self._action_ticks: dict[str, int] = {}

    def register(self, bus: EventBus) -> None:
        self._bus = bus
        bus.on(GameEvent.TIME_ADVANCED, self._on_tick)

    def _on_tick(self, event: Event, ctx: object) -> None:
        del event, ctx
        if self._bus is None:
            return
        with Session(self._engine) as session:
            npcs = [npc for npc in session.exec(select(NPC)).all() if npc.ai]
            if not npcs:
                return
            world = build_world_context(
                session,
                bus=self._bus,
                manager=self._manager,
                transaction=TransactionContext.create(
                    actor_id="npc_ai", correlation_id="npc_tick"
                ),
                session_id="npc_ai",
                rng=self._rng,
                meters=self._meters,
                effects=self._effects,
                clock=RoomRepo(session).world_clock(),
            )
            changed = False
            for npc in npcs:
                if self._maybe_move(npc, session, world):
                    changed = True
                self._maybe_act(npc, world)
            if changed:
                session.commit()

    def _maybe_move(
        self, npc: NPC, session: Session, world: StandaloneWorldContext
    ) -> bool:
        ai = npc.ai
        move_every = max(1, int(_as_int(ai.get("move_every"), 1)))
        count = self._ticks.get(npc.id, 0) + 1
        if count < move_every:
            self._ticks[npc.id] = count
            return False
        self._ticks[npc.id] = 0

        dest = self._next_room(npc, ai, session)
        if dest is None or dest == npc.current_room_id:
            return False

        from_room = npc.current_room_id
        npc.current_room_id = dest
        session.add(npc)
        broadcast_room_async(self._manager, from_room, f"{npc.name} leaves.")
        broadcast_room_async(self._manager, dest, f"{npc.name} arrives.")
        # NPC_MOVED drives encounter triggers for players in `dest` (see TriggerService).
        world.emit(
            GameEvent.NPC_MOVED,
            npc_id=npc.id,
            from_room_id=from_room,
            to_room_id=dest,
        )
        return True

    def _next_room(self, npc: NPC, ai: JsonObject, session: Session) -> str | None:
        mode = ai.get("mode")
        if mode == MODE_WANDER:
            return self._wander_target(npc, ai, session)
        if mode == MODE_PATROL:
            return self._patrol_target(npc, ai)
        return None

    def _wander_target(self, npc: NPC, ai: JsonObject, session: Session) -> str | None:
        exits = RoomRepo(session).exits(npc.current_room_id)
        targets = [ex.target_room_id for ex in exits]
        area = ai.get("area")
        if isinstance(area, str) and area:
            targets = [
                room_id for room_id in targets if _room_zone(session, room_id) == area
            ]
        if not targets:
            return None
        return self._rng.choice(sorted(targets))

    def _patrol_target(self, npc: NPC, ai: JsonObject) -> str | None:
        route = ai.get("route")
        if not isinstance(route, list) or not route:
            return None
        stops = [str(stop) for stop in route]
        try:
            idx = stops.index(npc.current_room_id)
        except ValueError:
            idx = -1
        return stops[(idx + 1) % len(stops)]

    def _maybe_act(self, npc: NPC, world: StandaloneWorldContext) -> None:
        for index, action in enumerate(_action_specs(npc.ai)):
            every_ticks = max(1, _as_int(action.get("every_ticks"), 1))
            key = f"{npc.id}:{index}"
            count = self._action_ticks.get(key, 0) + 1
            if count < every_ticks:
                self._action_ticks[key] = count
                continue
            self._action_ticks[key] = 0

            chance = _as_chance(action.get("chance"), 1.0)
            if chance < 1.0 and not self._rng.chance(chance):
                continue

            action_type = _action_type(action)
            text = _action_text(action, self._rng)
            message = _action_message(npc, action_type, text)
            if not message:
                continue
            world.narrate_room(npc.current_room_id, message)
            world.emit(
                GameEvent.NPC_ACTED,
                npc_id=npc.id,
                room_id=npc.current_room_id,
                action_type=action_type,
                text=text,
                message=message,
            )


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _as_chance(value: object, default: float) -> float:
    raw = (
        value
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else default
    )
    return max(0.0, min(1.0, float(raw)))


def _room_zone(session: Session, room_id: str) -> str | None:
    room = session.get(Room, room_id)
    return room.zone if room is not None else None


def _action_specs(ai: JsonObject) -> list[JsonObject]:
    actions = ai.get("actions")
    if isinstance(actions, dict):
        return [actions]
    if not isinstance(actions, list):
        return []
    return [entry for entry in actions if isinstance(entry, dict)]


def _action_type(action: JsonObject) -> str:
    raw = action.get("type", ACTION_EMOTE)
    action_type = raw if isinstance(raw, str) else ACTION_EMOTE
    return action_type if action_type in ACTION_TYPES else ACTION_EMOTE


def _action_text(action: JsonObject, rng: GameRng) -> str:
    lines = action.get("lines")
    if isinstance(lines, list):
        candidates = [str(line) for line in lines if str(line)]
        if candidates:
            return rng.choice(candidates)
    text = action.get("text", "")
    return str(text) if text is not None else ""


def _action_message(npc: NPC, action_type: str, text: str) -> str:
    if not text:
        return ""
    if action_type == ACTION_NARRATE:
        return text
    if action_type == ACTION_SAY:
        return f'{npc.name} says, "{text}"'
    return f"{npc.name} {text}"
