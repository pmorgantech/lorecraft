"""Transit line runtime: RouteSpec/RouteHooks wiring + board/disembark/schedule
commands (Sprint 29.2, docs/transit_systems.md §5, §11).

The Tier 1 MobileRouteService (Sprint 21) owns the state machine, scheduler
timing, and position interpolation -- this module only supplies line
semantics: doors (boarding gated on live vehicle state), ticket
validation/consumption, weather grounding, and narration. Minimap animation
(on_tick -> a `transit_update` WS push) is Sprint 29.3's job; `on_tick` here
is a no-op hook slot.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.events import GameEvent
from lorecraft.game.holders import Location
from lorecraft.models.mobile import MobileRouteState
from lorecraft.models.transit import TransitLine, TransitStop
from lorecraft.models.world import Room
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.repos.transit_repo import TransitRepo
from lorecraft.services.mobile_route import (
    MobileRouteService,
    RouteHooks,
    RouteSpec,
    Waypoint,
)

log = logging.getLogger(__name__)


def route_id_for_line(line_id: str) -> str:
    return f"transit:{line_id}"


class TransitService:
    def __init__(
        self,
        game_engine: Engine,
        mobile_routes: MobileRouteService,
        manager: ConnectionManager,
    ) -> None:
        self._game_engine = game_engine
        self._mobile_routes = mobile_routes
        self._manager = manager

    # -- lifespan wiring: build RouteSpec/RouteHooks per line ---------------

    def load_lines(self) -> None:
        """Register (and start) every TransitLine with a vehicle room and at
        least 2 stops. Idempotent: add_route()/start() never reset an
        already-running route, so calling this again (e.g. in tests) is safe."""
        with Session(self._game_engine) as session:
            repo = TransitRepo(session)
            for line in repo.all_lines():
                if line.vehicle_room_id is None:
                    continue  # 3b virtual journeys not yet built
                stops = repo.stops_for_line(line.id)
                if len(stops) < 2:
                    continue
                spec = self._build_spec(session, line, stops)
                if spec is None:
                    continue
                self._mobile_routes.add_route(spec, self._build_hooks(line))
                self._mobile_routes.start(spec.route_id)

    def _build_spec(
        self, session: Session, line: TransitLine, stops: list[TransitStop]
    ) -> RouteSpec | None:
        waypoints: list[Waypoint] = []
        for stop in stops:
            room = session.get(Room, stop.room_id)
            if room is None:
                continue
            waypoints.append(
                Waypoint(
                    position_id=stop.room_id,
                    x=room.map_x,
                    y=room.map_y,
                    dwell_ticks=stop.dwell_ticks,
                    travel_ticks=stop.travel_ticks,
                )
            )
        if len(waypoints) < 2:
            return None
        return RouteSpec(
            route_id=route_id_for_line(line.id),
            waypoints=tuple(waypoints),
            reverses=line.reverses,
            loop=line.loop,
            tick_pushes=0,
        )

    def _build_hooks(self, line: TransitLine) -> RouteHooks:
        def may_depart(
            session: Session, spec: RouteSpec, state: MobileRouteState
        ) -> str | None:
            del spec, state
            if not line.weather_sensitive:
                return None
            clock = RoomRepo(session).world_clock()
            if clock is not None and clock.weather in line.blocking_weather:
                return f"grounded: {clock.weather}"
            return None

        def on_depart(
            session: Session, spec: RouteSpec, state: MobileRouteState
        ) -> None:
            del session
            current_stop = spec.waypoints[state.current_index].position_id
            self._narrate(current_stop, f"The {line.name} pulls away.")
            self._narrate(line.vehicle_room_id, f"The {line.name} casts off.")

        def on_arrive(
            session: Session, spec: RouteSpec, state: MobileRouteState
        ) -> None:
            del session
            arrived_stop = spec.waypoints[state.current_index].position_id
            self._narrate(arrived_stop, f"The {line.name} arrives.")
            self._narrate(line.vehicle_room_id, f"The {line.name} pulls in.")

        return RouteHooks(
            may_depart=may_depart, on_depart=on_depart, on_arrive=on_arrive
        )

    def _narrate(self, room_id: str | None, text: str) -> None:
        if room_id is None:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no running event loop (e.g. in tests / scheduler-only contexts)
        asyncio.create_task(
            self._manager.broadcast_to_room(
                room_id,
                {"type": "feed_append", "content": text, "message_type": "room_event"},
            )
        )

    # -- player-facing commands ----------------------------------------

    def board(self, noun: str | None, ctx: GameContext) -> None:
        repo = TransitRepo(ctx.session)
        candidates = repo.lines_at_station(ctx.room.id)
        if not candidates:
            ctx.say("There's nothing to board here.")
            return

        line = self._match_line(candidates, noun)
        if line is None:
            if len(candidates) > 1:
                names = ", ".join(c.name for c in candidates)
                ctx.say(f"Board which line? ({names})")
            else:
                ctx.say(f"There's no {noun} here to board.")
            return

        state = ctx.session.get(MobileRouteState, route_id_for_line(line.id))
        if state is None or state.status != "at_stop":
            ctx.say(f"The {line.name} has already departed.")
            return
        stops = repo.stops_for_line(line.id)
        if stops[state.current_index].room_id != ctx.room.id:
            ctx.say(f"The {line.name} isn't here right now.")
            return
        if not stops[state.current_index].boarding:
            ctx.say(f"The {line.name} doesn't board passengers here.")
            return

        if line.ticket_item_id is not None:
            loc = Location("player", ctx.player.id)
            if ctx.stack_repo.quantity_of(loc, line.ticket_item_id) < 1:
                ctx.say(f"You need a ticket to board the {line.name}.")
                return
            if line.ticket_consumed:
                stack = ctx.stack_repo.find_fungible_stack(loc, line.ticket_item_id)
                if stack is not None and stack.id is not None:
                    ctx.item_location.destroy(stack.id, 1)

        vehicle_room = (
            ctx.room_repo.get(line.vehicle_room_id) if line.vehicle_room_id else None
        )
        if vehicle_room is None:
            ctx.say("Something is wrong with that vehicle.")
            return

        previous_room_id = ctx.room.id
        ctx.player.current_room_id = vehicle_room.id
        ctx.manager.move_player(ctx.player.id, previous_room_id, vehicle_room.id)
        ctx.room = vehicle_room
        ctx.say(f"You board the {line.name}.")
        ctx.tell_room(f"{ctx.player.username} boards the {line.name}.")
        ctx.tell_arrival(f"{ctx.player.username} boards from the platform.")
        ctx.push_update("room_id", vehicle_room.id)
        ctx.queue_event(
            GameEvent.TRANSIT_BOARDED,
            player_id=ctx.player.id,
            line_id=line.id,
            room_id=previous_room_id,
        )

    def disembark(self, noun: str | None, ctx: GameContext) -> None:
        del noun
        line = TransitRepo(ctx.session).line_for_vehicle_room(ctx.room.id)
        if line is None:
            ctx.say("You're not aboard anything.")
            return

        state = ctx.session.get(MobileRouteState, route_id_for_line(line.id))
        if state is None or state.status != "at_stop":
            ctx.say(f"You can't disembark the {line.name} while it's moving.")
            return
        stops = TransitRepo(ctx.session).stops_for_line(line.id)
        current_stop = stops[state.current_index]
        if not current_stop.boarding:
            ctx.say(f"The {line.name} doesn't open its doors here.")
            return

        station = ctx.room_repo.get(current_stop.room_id)
        if station is None:
            ctx.say("Something is wrong with that station.")
            return

        previous_room_id = ctx.room.id
        ctx.player.current_room_id = station.id
        ctx.manager.move_player(ctx.player.id, previous_room_id, station.id)
        ctx.room = station
        ctx.say(f"You disembark from the {line.name}.")
        ctx.tell_room(f"{ctx.player.username} disembarks from the {line.name}.")
        ctx.tell_arrival(f"{ctx.player.username} disembarks from the {line.name}.")
        ctx.push_update("room_id", station.id)
        ctx.queue_event(
            GameEvent.TRANSIT_DISEMBARKED,
            player_id=ctx.player.id,
            line_id=line.id,
            room_id=station.id,
        )

    def schedule(self, noun: str | None, ctx: GameContext) -> None:
        repo = TransitRepo(ctx.session)
        line = repo.line_for_vehicle_room(ctx.room.id)
        if line is None:
            line = self._match_line(repo.lines_at_station(ctx.room.id), noun)
        if line is None:
            ctx.say("No transit line schedule available here.")
            return

        state = ctx.session.get(MobileRouteState, route_id_for_line(line.id))
        stops = repo.stops_for_line(line.id)
        lines_out = [f"{line.name} ({line.mode}, {line.service_type}):"]
        for i, stop in enumerate(stops):
            room = ctx.room_repo.get(stop.room_id)
            room_name = room.name if room is not None else stop.room_id
            marker = (
                " <- here" if state is not None and state.current_index == i else ""
            )
            boarding_note = "" if stop.boarding else " (no boarding)"
            lines_out.append(f"  {i + 1}. {room_name}{boarding_note}{marker}")
        if state is not None:
            lines_out.append(f"Status: {state.status}")
        ctx.say("\n".join(lines_out))

    def _match_line(
        self, candidates: list[TransitLine], noun: str | None
    ) -> TransitLine | None:
        if not candidates:
            return None
        if noun is None:
            return candidates[0] if len(candidates) == 1 else None
        query = noun.strip().lower()
        for line in candidates:
            if line.name.lower() == query or line.id.lower() == query:
                return line
        for line in candidates:
            if query in line.name.lower():
                return line
        return None
