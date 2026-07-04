"""Tests for Sprint 29.2: transit vehicle wiring + board/disembark/schedule
commands."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.engine import CommandEngine
from lorecraft.game.events import Event, EventBus, GameEvent
from lorecraft.game.holders import Location
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rng import GameRng
from lorecraft.game.rules import RuleEngine
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.mobile import MobileRouteState
from lorecraft.models.transit import TransitLine, TransitStop
from lorecraft.models.world import Item, Room, WorldClock
from lorecraft.models.player import Player, PlayerStats
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.container import ServiceContainer
from lorecraft.services.effects import EffectService
from lorecraft.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.services.meters import MeterService
from lorecraft.services.mobile_route import MobileRouteService
from lorecraft.services.scheduler import SchedulerService
from lorecraft.services.transit import TransitService, route_id_for_line

PIER_ID = "pier"
ROCK_ID = "rock"
VEHICLE_ROOM_ID = "ferry_deck"
LINE_ID = "coastal_ferry"


def _seed(session: Session) -> None:
    session.add(Room(id=PIER_ID, name="Pier", description="d", map_x=0, map_y=0))
    session.add(Room(id=ROCK_ID, name="Gull Rock", description="d", map_x=2, map_y=1))
    session.add(
        Room(id=VEHICLE_ROOM_ID, name="Ferry Deck", description="d", map_x=0, map_y=0)
    )
    session.add(Item(id="ferry_token", name="ferry token", description="d"))
    session.add(
        TransitLine(
            id=LINE_ID,
            name="Coastal Ferry",
            mode="ferry",
            vehicle_room_id=VEHICLE_ROOM_ID,
            ticket_item_id="ferry_token",
            ticket_consumed=True,
            weather_sensitive=True,
            blocking_weather=["fog"],
        )
    )
    session.add(
        TransitStop(
            line_id=LINE_ID, room_id=PIER_ID, sequence=0, dwell_ticks=5, travel_ticks=20
        )
    )
    session.add(
        TransitStop(
            line_id=LINE_ID, room_id=ROCK_ID, sequence=1, dwell_ticks=5, travel_ticks=0
        )
    )
    session.add(WorldClock(game_epoch=0.0, real_epoch=0.0, weather="clear"))
    session.add(
        Player(
            id="player-1",
            username="tester",
            current_room_id=PIER_ID,
            respawn_room_id=PIER_ID,
        )
    )
    session.add(PlayerStats(player_id="player-1"))
    session.commit()


def _build() -> tuple[CommandEngine, GameContext, Session, TransitService]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    _seed(session)

    bus = EventBus()
    manager = ConnectionManager()
    scheduler = SchedulerService(engine, GameRng())
    scheduler.register(bus)
    mobile_routes = MobileRouteService(engine, scheduler)
    mobile_routes.register(bus)
    transit = TransitService(engine, mobile_routes, manager)
    transit.load_lines()

    registry = CommandRegistry()
    register_all_commands(registry, ServiceContainer.build(), transit=transit)

    player = session.get(Player, "player-1")
    assert player is not None
    room = session.get(Room, PIER_ID)
    assert room is not None
    ctx = GameContext(
        player=player,
        room=room,
        clock=session.get(WorldClock, 1),
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=GameRng(seed=1),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=manager,
        bus=bus,
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
    return CommandEngine(registry, RuleEngine()), ctx, session, transit


@pytest.fixture
def built() -> Iterator[tuple[CommandEngine, GameContext, Session, TransitService]]:
    cmd_engine, ctx, session, transit = _build()
    yield cmd_engine, ctx, session, transit
    session.close()


class TestLoadLines:
    def test_creates_at_stop_runtime_state(
        self, built: tuple[CommandEngine, GameContext, Session, TransitService]
    ) -> None:
        _cmd_engine, _ctx, session, _transit = built
        state = session.get(MobileRouteState, route_id_for_line(LINE_ID))
        assert state is not None
        assert state.status == "at_stop"
        assert state.current_index == 0


class TestBoard:
    def test_board_requires_ticket(
        self, built: tuple[CommandEngine, GameContext, Session, TransitService]
    ) -> None:
        cmd_engine, ctx, _session, _transit = built

        cmd_engine.handle_command("board", ctx)

        assert any("need a ticket" in m for m in ctx.messages)
        assert ctx.player.current_room_id == PIER_ID

    def test_board_consumes_ticket_and_moves_player(
        self, built: tuple[CommandEngine, GameContext, Session, TransitService]
    ) -> None:
        cmd_engine, ctx, session, _transit = built
        ctx.item_location.spawn("ferry_token", Location("player", ctx.player.id))
        session.commit()

        cmd_engine.handle_command("board", ctx)

        assert ctx.player.current_room_id == VEHICLE_ROOM_ID
        assert (
            ctx.stack_repo.quantity_of(Location("player", ctx.player.id), "ferry_token")
            == 0
        )
        assert any("board the Coastal Ferry" in m for m in ctx.messages)

    def test_board_rejects_when_vehicle_at_a_different_stop(
        self, built: tuple[CommandEngine, GameContext, Session, TransitService]
    ) -> None:
        """Gull Rock is a stop on this line, but the ferry is docked at the
        Pier (current_index 0) -- boarding from the wrong stop must fail."""
        cmd_engine, ctx, session, _transit = built
        rock = session.get(Room, ROCK_ID)
        assert rock is not None
        ctx.room = rock
        ctx.player.current_room_id = ROCK_ID

        cmd_engine.handle_command("board", ctx)

        assert any("isn't here" in m for m in ctx.messages)

    def test_board_fails_when_vehicle_in_transit(
        self, built: tuple[CommandEngine, GameContext, Session, TransitService]
    ) -> None:
        cmd_engine, ctx, session, _transit = built
        state = session.get(MobileRouteState, route_id_for_line(LINE_ID))
        assert state is not None
        state.status = "in_transit"
        session.add(state)
        session.commit()

        cmd_engine.handle_command("board", ctx)

        assert any("already departed" in m for m in ctx.messages)


class TestDisembark:
    def test_disembark_moves_player_to_station(
        self, built: tuple[CommandEngine, GameContext, Session, TransitService]
    ) -> None:
        cmd_engine, ctx, session, _transit = built
        ctx.item_location.spawn("ferry_token", Location("player", ctx.player.id))
        session.commit()
        cmd_engine.handle_command("board", ctx)

        cmd_engine.handle_command("disembark", ctx)

        assert ctx.player.current_room_id == PIER_ID
        assert any("disembark" in m for m in ctx.messages)

    def test_disembark_without_boarding(
        self, built: tuple[CommandEngine, GameContext, Session, TransitService]
    ) -> None:
        cmd_engine, ctx, _session, _transit = built

        cmd_engine.handle_command("disembark", ctx)

        assert any("not aboard" in m for m in ctx.messages)


class TestSchedule:
    def test_schedule_lists_stops(
        self, built: tuple[CommandEngine, GameContext, Session, TransitService]
    ) -> None:
        cmd_engine, ctx, _session, _transit = built

        cmd_engine.handle_command("schedule", ctx)

        joined = "\n".join(ctx.messages)
        assert "Pier" in joined and "Gull Rock" in joined
        assert "here" in joined


class TestWeatherGrounding:
    def test_line_halts_when_blocking_weather_active(
        self, built: tuple[CommandEngine, GameContext, Session, TransitService]
    ) -> None:
        _cmd_engine, ctx, session, _transit = built
        wc = session.get(WorldClock, 1)
        assert wc is not None
        wc.weather = "fog"
        session.add(wc)
        session.commit()

        # dwell_ticks=5 at the first stop -> a depart-check job is due at
        # epoch 5; may_depart's weather check should halt it rather than
        # letting it enter transit.
        ctx.bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 5.0}), ctx=None)

        state = session.get(MobileRouteState, route_id_for_line(LINE_ID))
        assert state is not None
        assert state.status == "halted"

    def test_line_departs_when_weather_is_clear(
        self, built: tuple[CommandEngine, GameContext, Session, TransitService]
    ) -> None:
        _cmd_engine, ctx, session, _transit = built

        ctx.bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 5.0}), ctx=None)

        state = session.get(MobileRouteState, route_id_for_line(LINE_ID))
        assert state is not None
        assert state.status == "in_transit"
