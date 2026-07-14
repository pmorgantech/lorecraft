"""Mobile-route backed NPC patrol hooks."""

from __future__ import annotations

import logging

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.game.world_context import (
    broadcast_room_async,
    build_world_context,
)
from lorecraft.engine.models.mobile import MobileRouteState
from lorecraft.engine.models.world import NPC, Room
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.services.mobile_route import (
    MobileRouteService,
    RouteHooks,
    RouteSpec,
    Waypoint,
)

log = logging.getLogger(__name__)

MODE_ROUTE = "route"


class NpcRouteLoader:
    """Registers NPC ``ai.mode: route`` specs with ``MobileRouteService``."""

    def __init__(
        self,
        game_engine: Engine,
        mobile_routes: MobileRouteService,
        manager: ConnectionManager,
        bus: EventBus,
        rng: GameRng,
        meters: MeterService,
        effects: EffectService,
    ) -> None:
        self._engine = game_engine
        self._mobile_routes = mobile_routes
        self._manager = manager
        self._bus = bus
        self._rng = rng
        self._meters = meters
        self._effects = effects

    def load_routes(self) -> None:
        with Session(self._engine) as session:
            npcs = [npc for npc in session.exec(select(NPC)).all() if npc.ai]
            for npc in npcs:
                spec = build_npc_route_spec(session, npc)
                if spec is None:
                    continue
                self._mobile_routes.add_route(spec, self._hooks_for(npc.id))
                self._mobile_routes.start(spec.route_id)

    def _hooks_for(self, npc_id: str) -> RouteHooks:
        def on_depart(
            session: Session, spec: RouteSpec, state: MobileRouteState
        ) -> None:
            npc = session.get(NPC, npc_id)
            if npc is None:
                return
            room_id = spec.waypoints[state.current_index].position_id
            broadcast_room_async(self._manager, room_id, f"{npc.name} leaves.")

        def on_arrive(
            session: Session, spec: RouteSpec, state: MobileRouteState
        ) -> None:
            npc = session.get(NPC, npc_id)
            if npc is None:
                return
            previous_room_id = npc.current_room_id
            room_id = spec.waypoints[state.current_index].position_id
            npc.current_room_id = room_id
            session.add(npc)
            session.commit()
            broadcast_room_async(self._manager, room_id, f"{npc.name} arrives.")
            world = build_world_context(
                session,
                bus=self._bus,
                manager=self._manager,
                transaction=TransactionContext.create(
                    actor_id="npc_ai", correlation_id=f"npc_route:{npc.id}"
                ),
                session_id="npc_ai",
                rng=self._rng,
                meters=self._meters,
                effects=self._effects,
                clock=RoomRepo(session).world_clock(),
            )
            self._bus.emit(
                Event(
                    GameEvent.NPC_MOVED,
                    {
                        "npc_id": npc.id,
                        "from_room_id": previous_room_id,
                        "to_room_id": room_id,
                    },
                ),
                world,
            )

        return RouteHooks(on_depart=on_depart, on_arrive=on_arrive)


def build_npc_route_spec(session: Session, npc: NPC) -> RouteSpec | None:
    ai = npc.ai
    if ai.get("mode") != MODE_ROUTE:
        return None
    raw_route = ai.get("route")
    if not isinstance(raw_route, list) or len(raw_route) < 2:
        return None
    room_ids = [room_id for room_id in (str(item) for item in raw_route) if room_id]
    rooms = {room.id: room for room in session.exec(select(Room)).all()}
    waypoints: list[Waypoint] = []
    for room_id in room_ids:
        room = rooms.get(room_id)
        if room is None:
            log.warning("npc_route_missing_room npc=%s room=%s", npc.id, room_id)
            return None
        waypoints.append(
            Waypoint(
                position_id=room.id,
                x=room.map_x,
                y=room.map_y,
                dwell_ticks=float(_as_int(ai.get("dwell_ticks"), 1)),
                travel_ticks=float(_as_int(ai.get("travel_ticks"), 1)),
            )
        )
    return RouteSpec(
        route_id=f"npc:{npc.id}",
        waypoints=tuple(waypoints),
        reverses=_as_bool(ai.get("reverses"), True),
        loop=_as_bool(ai.get("loop"), False),
        tick_pushes=max(0, _as_int(ai.get("tick_pushes"), 0)),
    )


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _as_bool(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default
