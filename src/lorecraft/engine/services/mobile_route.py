"""Scheduled mobile entity ("moving room") — the generic route runner.

See docs/engine_core.md §3.8. A state machine advancing an entity along a
waypoint route on scheduler time, with position interpolation for the
minimap. Transit line *semantics* (express/local, tickets, doors, weather)
stay Tier 2 — they plug in via RouteHooks. All timing runs through the
existing SchedulerService with job_type="mobile_route" — no second timing
mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.models.mobile import MobileRouteState
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.scheduler import SchedulerService


@dataclass(frozen=True)
class Waypoint:
    """A stop on a route.

    Args:
        position_id: For transit, a station room_id.
        x, y: Map coords for interpolation.
        dwell_ticks: Wait at this waypoint before departing.
        travel_ticks: Travel time to the NEXT waypoint.
    """

    position_id: str
    x: int
    y: int
    dwell_ticks: float
    travel_ticks: float


@dataclass(frozen=True)
class RouteSpec:
    route_id: str
    waypoints: tuple[Waypoint, ...]  # len >= 2
    reverses: bool = True  # ping-pong at ends; False + loop=True = circular
    loop: bool = False
    tick_pushes: int = 0  # interpolated position pushes per segment (0 = none)


def _no_halt(session: Session, spec: RouteSpec, state: MobileRouteState) -> str | None:
    del session, spec, state
    return None


def _noop_session_hook(
    session: Session, spec: RouteSpec, state: MobileRouteState
) -> None:
    del session, spec, state


def _noop_tick_hook(spec: RouteSpec, state: MobileRouteState, progress: float) -> None:
    del spec, state, progress


@dataclass(frozen=True)
class RouteHooks:
    may_depart: Callable[[Session, RouteSpec, MobileRouteState], str | None] = _no_halt
    on_depart: Callable[[Session, RouteSpec, MobileRouteState], None] = (
        _noop_session_hook
    )
    on_arrive: Callable[[Session, RouteSpec, MobileRouteState], None] = (
        _noop_session_hook
    )
    on_tick: Callable[[RouteSpec, MobileRouteState, float], None] = _noop_tick_hook


def _advance_indices(
    spec: RouteSpec, next_index: int, direction: int
) -> tuple[int, int, int]:
    """Compute (new_current_index, new_next_index, new_direction) on arrival
    at `next_index`. reverses=True ping-pongs at the ends regardless of
    `loop`; loop=True only takes effect when reverses=False (circular)."""
    n = len(spec.waypoints)
    new_current = next_index
    if spec.reverses:
        candidate = new_current + direction
        if candidate < 0 or candidate >= n:
            direction = -direction
            candidate = new_current + direction
        new_next = candidate
    elif spec.loop:
        new_next = (new_current + direction) % n
    else:
        new_next = max(0, min(n - 1, new_current + direction))
    return new_current, new_next, direction


class MobileRouteService:
    """Engine-holding schedulable — exactly the SchedulerService shape."""

    def __init__(self, game_engine: Engine, scheduler: SchedulerService) -> None:
        self._game_engine = game_engine
        self._scheduler = scheduler
        self._bus: EventBus | None = None
        self._specs: dict[str, RouteSpec] = {}
        self._hooks: dict[str, RouteHooks] = {}

    def register(self, bus: EventBus) -> None:
        self._bus = bus
        bus.on(GameEvent.SCHEDULED_JOB_DUE, self._on_scheduled_job_due)

    def add_route(self, spec: RouteSpec, hooks: RouteHooks) -> None:
        """Register a route's spec/hooks (at lifespan). Ensures a runtime
        MobileRouteState row exists — never resets an existing one, so a
        server restart resumes rather than re-initializes an in-progress
        route."""
        self._specs[spec.route_id] = spec
        self._hooks[spec.route_id] = hooks
        with Session(self._game_engine) as session:
            if session.get(MobileRouteState, spec.route_id) is None:
                session.add(MobileRouteState(route_id=spec.route_id))
                session.commit()

    def start(self, route_id: str) -> None:
        """Kick off the cycle for a route currently at_stop or halted. A
        no-op if already in_transit (already running)."""
        with Session(self._game_engine) as session:
            state = session.get(MobileRouteState, route_id)
            if state is None or state.status == "in_transit":
                return
            state.status = "at_stop"
            session.add(state)
            session.commit()
            self._schedule_depart_check(session, route_id, self._current_epoch(session))

    def halt(self, route_id: str) -> None:
        """Force a route to halted. A route whose spec disappeared on restart
        is halted and logged, not crashed — callers can call this defensively
        even for an unregistered route_id."""
        with Session(self._game_engine) as session:
            state = session.get(MobileRouteState, route_id)
            if state is not None:
                state.status = "halted"
                session.add(state)
                session.commit()

    def resume(self, route_id: str) -> None:
        """Manual control: immediately re-check may_depart for a halted
        route rather than waiting for the next scheduled retry."""
        with Session(self._game_engine) as session:
            state = session.get(MobileRouteState, route_id)
            if state is None or state.status != "halted":
                return
            self._try_depart(session, route_id, state, self._current_epoch(session))

    def progress(self, state: MobileRouteState, now_epoch: float) -> float:
        """(now-depart)/(arrive-depart), clamped to [0, 1]."""
        if state.depart_epoch is None or state.arrive_epoch is None:
            return 0.0
        span = state.arrive_epoch - state.depart_epoch
        if span <= 0:
            return 1.0
        return max(0.0, min(1.0, (now_epoch - state.depart_epoch) / span))

    def position(
        self, spec: RouteSpec, state: MobileRouteState, now_epoch: float
    ) -> tuple[float, float]:
        """Interpolated (x, y) between the current and next waypoint."""
        current_wp = spec.waypoints[state.current_index]
        next_wp = spec.waypoints[state.next_index]
        t = self.progress(state, now_epoch)
        x = current_wp.x + (next_wp.x - current_wp.x) * t
        y = current_wp.y + (next_wp.y - current_wp.y) * t
        return (x, y)

    # -- internal: state machine -------------------------------------------

    def _current_epoch(self, session: Session) -> float:
        clock = RoomRepo(session).world_clock()
        return clock.game_epoch if clock is not None else 0.0

    def _schedule_depart_check(
        self, session: Session, route_id: str, now: float
    ) -> None:
        spec = self._specs.get(route_id)
        state = session.get(MobileRouteState, route_id)
        if spec is None or state is None:
            return
        current_wp = spec.waypoints[state.current_index]
        at_epoch = now + current_wp.dwell_ticks
        self._scheduler.schedule(
            "mobile_route",
            at_epoch,
            {"route_id": route_id, "action": "depart"},
        )

    def _try_depart(
        self, session: Session, route_id: str, state: MobileRouteState, now: float
    ) -> None:
        spec = self._specs.get(route_id)
        hooks = self._hooks.get(route_id)
        if spec is None or hooks is None:
            # Route whose spec disappeared on restart is halted, not crashed.
            state.status = "halted"
            session.add(state)
            session.commit()
            return

        reason = hooks.may_depart(session, spec, state)
        if reason is not None:
            state.status = "halted"
            session.add(state)
            session.commit()
            self._schedule_depart_check(session, route_id, now)
            return

        current_wp = spec.waypoints[state.current_index]
        state.status = "in_transit"
        state.depart_epoch = now
        state.arrive_epoch = now + current_wp.travel_ticks
        session.add(state)
        session.commit()
        hooks.on_depart(session, spec, state)

        self._scheduler.schedule(
            "mobile_route",
            state.arrive_epoch,
            {"route_id": route_id, "action": "arrive"},
        )
        if spec.tick_pushes > 0:
            for k in range(1, spec.tick_pushes + 1):
                fraction = k / (spec.tick_pushes + 1)
                tick_epoch = now + current_wp.travel_ticks * fraction
                self._scheduler.schedule(
                    "mobile_route",
                    tick_epoch,
                    {"route_id": route_id, "action": "tick"},
                )

    def _handle_depart_check(self, route_id: str, now: float) -> None:
        with Session(self._game_engine) as session:
            state = session.get(MobileRouteState, route_id)
            if state is None or state.status not in ("at_stop", "halted"):
                return  # stale job (e.g. already departed since scheduling)
            self._try_depart(session, route_id, state, now)

    def _handle_arrive(self, route_id: str) -> None:
        with Session(self._game_engine) as session:
            spec = self._specs.get(route_id)
            hooks = self._hooks.get(route_id)
            state = session.get(MobileRouteState, route_id)
            if spec is None or hooks is None or state is None:
                return
            if state.status != "in_transit":
                return  # stale job (e.g. force-halted mid-transit)

            arrive_epoch = state.arrive_epoch
            new_current, new_next, new_direction = _advance_indices(
                spec, state.next_index, state.direction
            )
            state.current_index = new_current
            state.next_index = new_next
            state.direction = new_direction
            state.status = "at_stop"
            state.depart_epoch = None
            state.arrive_epoch = None
            session.add(state)
            session.commit()
            hooks.on_arrive(session, spec, state)

            self._schedule_depart_check(session, route_id, arrive_epoch or 0.0)

    def _handle_tick(self, route_id: str, now: float) -> None:
        with Session(self._game_engine) as session:
            spec = self._specs.get(route_id)
            hooks = self._hooks.get(route_id)
            state = session.get(MobileRouteState, route_id)
            if spec is None or hooks is None or state is None:
                return
            if state.status != "in_transit":
                return
            progress = self.progress(state, now)
        hooks.on_tick(spec, state, progress)

    def _on_scheduled_job_due(self, event: Event, ctx: object) -> None:
        del ctx
        if event.payload.get("job_type") != "mobile_route":
            return
        inner = event.payload.get("payload")
        if not isinstance(inner, dict):
            return
        route_id = inner.get("route_id")
        action = inner.get("action")
        current_epoch = event.payload.get("current_epoch")
        if not isinstance(route_id, str) or not isinstance(current_epoch, (int, float)):
            return
        now = float(current_epoch)

        if action == "depart":
            self._handle_depart_check(route_id, now)
        elif action == "arrive":
            self._handle_arrive(route_id)
        elif action == "tick":
            self._handle_tick(route_id, now)
