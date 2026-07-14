"""NPC-specific hooks on the generic mobile route runner."""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.world import NPC, Room, WorldClock
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.services.mobile_route import MobileRouteService
from lorecraft.engine.services.scheduler import SchedulerService
from lorecraft.features.npc_ai.routes import NpcRouteLoader, build_npc_route_spec


def _engine() -> Engine:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        session.add(Room(id="a", name="A", description="d", map_x=0, map_y=0))
        session.add(Room(id="b", name="B", description="d", map_x=1, map_y=0))
        session.add(WorldClock(game_epoch=0.0, real_epoch=0.0))
        session.add(
            NPC(
                id="wren",
                name="Wren",
                description="d",
                current_room_id="a",
                home_room_id="a",
                dialogue_tree_id="none",
                ai={
                    "mode": "route",
                    "route": ["a", "b"],
                    "dwell_ticks": 1,
                    "travel_ticks": 1,
                },
            )
        )
        session.commit()
    return engine


def _advance(bus: EventBus, epoch: float) -> None:
    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": epoch}), None)


def test_build_npc_route_spec_reads_room_waypoints() -> None:
    engine = _engine()
    with Session(engine) as session:
        npc = session.get(NPC, "wren")
        assert npc is not None
        spec = build_npc_route_spec(session, npc)

    assert spec is not None
    assert spec.route_id == "npc:wren"
    assert [waypoint.position_id for waypoint in spec.waypoints] == ["a", "b"]


def test_npc_route_loader_moves_npc_on_scheduler_arrival() -> None:
    engine = _engine()
    bus = EventBus()
    scheduler = SchedulerService(engine, GameRng(seed=1))
    scheduler.register(bus)
    mobile_routes = MobileRouteService(engine, scheduler)
    mobile_routes.register(bus)
    moved: list[tuple[str, str]] = []
    bus.on(
        GameEvent.NPC_MOVED,
        lambda event, _ctx: moved.append(
            (str(event.payload["from_room_id"]), str(event.payload["to_room_id"]))
        ),
    )

    NpcRouteLoader(
        engine,
        mobile_routes,
        ConnectionManager(),
        bus,
        GameRng(seed=1),
        MeterService(engine, GameRng()),
        EffectService(engine, GameRng()),
    ).load_routes()
    _advance(bus, 1.0)
    _advance(bus, 2.0)

    with Session(engine) as session:
        npc = session.get(NPC, "wren")
        assert npc is not None
        assert npc.current_room_id == "b"
    assert moved == [("a", "b")]
