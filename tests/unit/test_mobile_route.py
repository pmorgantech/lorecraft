"""Unit tests for MobileRouteService (engine_core.md §3.8)."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.models.mobile import MobileRouteState
from lorecraft.models.world import WorldClock
from lorecraft.engine.services.mobile_route import (
    MobileRouteService,
    RouteHooks,
    RouteSpec,
    Waypoint,
)
from lorecraft.engine.services.scheduler import SchedulerService


def _engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        session.add(WorldClock(game_epoch=0.0, real_epoch=0.0))
        session.commit()
    return engine


def _build(engine):
    bus = EventBus()
    scheduler = SchedulerService(engine, GameRng())
    scheduler.register(bus)
    service = MobileRouteService(engine, scheduler)
    service.register(bus)
    return bus, service


def _two_stop_spec(**overrides) -> RouteSpec:
    waypoints = (
        Waypoint(position_id="stop_a", x=0, y=0, dwell_ticks=5.0, travel_ticks=10.0),
        Waypoint(position_id="stop_b", x=10, y=0, dwell_ticks=5.0, travel_ticks=10.0),
    )
    return RouteSpec(route_id="line_1", waypoints=waypoints, **overrides)


def _advance(bus: EventBus, epoch: float) -> None:
    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": epoch}), ctx=None)


class TestAddRoute:
    def test_creates_runtime_state_row(self) -> None:
        engine = _engine()
        _, service = _build(engine)

        service.add_route(_two_stop_spec(), RouteHooks())

        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "at_stop"
            assert state.current_index == 0
            assert state.next_index == 1

    def test_does_not_reset_existing_state(self) -> None:
        engine = _engine()
        _, service = _build(engine)
        service.add_route(_two_stop_spec(), RouteHooks())
        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            state.current_index = 1
            state.status = "halted"
            session.add(state)
            session.commit()

        service.add_route(_two_stop_spec(), RouteHooks())

        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "halted"
            assert state.current_index == 1


class TestDepartArriveCycle:
    def test_full_round_trip_ping_pongs_at_ends(self) -> None:
        engine = _engine()
        bus, service = _build(engine)
        service.add_route(_two_stop_spec(), RouteHooks())

        service.start("line_1")  # schedules depart at epoch 5 (0 + dwell)

        _advance(bus, 5.0)  # departs stop_a; arrives at epoch 15
        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "in_transit"
            assert state.depart_epoch == 5.0
            assert state.arrive_epoch == 15.0

        _advance(bus, 15.0)  # arrives at stop_b; schedules next depart at 20
        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "at_stop"
            assert state.current_index == 1
            assert state.next_index == 0
            assert state.direction == -1

        _advance(bus, 20.0)  # departs stop_b; arrives at epoch 30
        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "in_transit"
            assert state.depart_epoch == 20.0
            assert state.arrive_epoch == 30.0

        _advance(bus, 30.0)  # arrives back at stop_a; reverses again
        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "at_stop"
            assert state.current_index == 0
            assert state.next_index == 1
            assert state.direction == 1

    def test_start_is_noop_while_in_transit(self) -> None:
        engine = _engine()
        bus, service = _build(engine)
        service.add_route(_two_stop_spec(), RouteHooks())
        service.start("line_1")
        _advance(bus, 5.0)

        service.start("line_1")  # must not reset the in-flight leg

        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "in_transit"
            assert state.depart_epoch == 5.0


class TestLoopWraparound:
    def test_circular_route_cycles_without_reversing(self) -> None:
        engine = _engine()
        bus, service = _build(engine)
        waypoints = (
            Waypoint(position_id="a", x=0, y=0, dwell_ticks=1.0, travel_ticks=1.0),
            Waypoint(position_id="b", x=1, y=0, dwell_ticks=1.0, travel_ticks=1.0),
            Waypoint(position_id="c", x=2, y=0, dwell_ticks=1.0, travel_ticks=1.0),
        )
        spec = RouteSpec(
            route_id="loop_1", waypoints=waypoints, reverses=False, loop=True
        )
        service.add_route(spec, RouteHooks())
        service.start("loop_1")

        seen_current_indices: list[int] = []
        epoch = 0.0
        for _ in range(6):  # three full depart/arrive legs
            epoch += 1.0
            _advance(bus, epoch)  # depart
            epoch += 1.0
            _advance(bus, epoch)  # arrive
            with Session(engine) as session:
                state = session.get(MobileRouteState, "loop_1")
                assert state is not None
                seen_current_indices.append(state.current_index)

        assert seen_current_indices == [1, 2, 0, 1, 2, 0]


class TestMayDepartHalt:
    def test_halt_reason_parks_route_and_reschedules_retry(self) -> None:
        engine = _engine()
        bus, service = _build(engine)
        allow = {"value": False}

        def may_depart(session, spec, state):
            del session, spec, state
            return None if allow["value"] else "storm"

        service.add_route(_two_stop_spec(), RouteHooks(may_depart=may_depart))
        service.start("line_1")

        _advance(bus, 5.0)  # may_depart says no -> halted, retry scheduled for 10
        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "halted"

        _advance(bus, 10.0)  # still halted
        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "halted"

        allow["value"] = True
        _advance(bus, 15.0)  # now departs
        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "in_transit"
            assert state.depart_epoch == 15.0

    def test_resume_re_checks_immediately(self) -> None:
        engine = _engine()
        bus, service = _build(engine)
        allow = {"value": False}

        def may_depart(session, spec, state):
            del session, spec, state
            return None if allow["value"] else "storm"

        service.add_route(_two_stop_spec(), RouteHooks(may_depart=may_depart))
        service.start("line_1")
        _advance(bus, 5.0)
        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "halted"

        allow["value"] = True
        service.resume("line_1")  # immediate re-check, doesn't wait for retry job

        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "in_transit"


class TestHalt:
    def test_halt_forces_status_regardless_of_current_state(self) -> None:
        engine = _engine()
        _, service = _build(engine)
        service.add_route(_two_stop_spec(), RouteHooks())
        service.start("line_1")

        service.halt("line_1")

        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "halted"

    def test_halt_on_unknown_route_is_a_noop(self) -> None:
        engine = _engine()
        _, service = _build(engine)
        service.halt("no-such-route")  # must not raise


class TestSpecDisappearedOnRestart:
    def test_missing_spec_at_depart_time_halts_instead_of_crashing(self) -> None:
        engine = _engine()
        bus, service = _build(engine)
        service.add_route(_two_stop_spec(), RouteHooks())
        service.start("line_1")

        # Simulate a restart where the owning feature never re-registered
        # this route's spec/hooks before the scheduled job fires.
        service._specs.clear()
        service._hooks.clear()

        _advance(bus, 5.0)

        with Session(engine) as session:
            state = session.get(MobileRouteState, "line_1")
            assert state is not None
            assert state.status == "halted"


class TestTickPushes:
    def test_on_tick_fires_with_interpolated_progress(self) -> None:
        engine = _engine()
        bus, service = _build(engine)
        observed: list[float] = []

        def on_tick(spec, state, progress):
            del spec, state
            observed.append(progress)

        spec = _two_stop_spec(tick_pushes=1)
        service.add_route(spec, RouteHooks(on_tick=on_tick))
        service.start("line_1")

        _advance(bus, 5.0)  # departs at 5, arrives at 15, tick scheduled at 10
        _advance(bus, 10.0)

        assert observed == [0.5]

    def test_no_tick_scheduled_when_tick_pushes_is_zero(self) -> None:
        engine = _engine()
        bus, service = _build(engine)
        observed: list[float] = []

        def on_tick(spec, state, progress):
            del spec, state
            observed.append(progress)

        service.add_route(_two_stop_spec(), RouteHooks(on_tick=on_tick))
        service.start("line_1")

        _advance(bus, 5.0)
        _advance(bus, 10.0)
        _advance(bus, 15.0)

        assert observed == []


class TestProgressAndPosition:
    def test_progress_clamped_to_unit_interval(self) -> None:
        service = MobileRouteService.__new__(MobileRouteService)
        state = MobileRouteState(route_id="r", depart_epoch=10.0, arrive_epoch=20.0)
        assert service.progress(state, 5.0) == 0.0
        assert service.progress(state, 10.0) == 0.0
        assert service.progress(state, 15.0) == 0.5
        assert service.progress(state, 20.0) == 1.0
        assert service.progress(state, 25.0) == 1.0

    def test_progress_with_no_active_leg_is_zero(self) -> None:
        service = MobileRouteService.__new__(MobileRouteService)
        state = MobileRouteState(route_id="r")
        assert service.progress(state, 100.0) == 0.0

    def test_position_interpolates_between_waypoints(self) -> None:
        service = MobileRouteService.__new__(MobileRouteService)
        spec = _two_stop_spec()
        state = MobileRouteState(
            route_id="r",
            current_index=0,
            next_index=1,
            depart_epoch=0.0,
            arrive_epoch=10.0,
        )
        assert service.position(spec, state, 0.0) == (0.0, 0.0)
        assert service.position(spec, state, 5.0) == (5.0, 0.0)
        assert service.position(spec, state, 10.0) == (10.0, 0.0)
