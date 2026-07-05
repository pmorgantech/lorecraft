"""Tests for Sprint 29.2: transit vehicle wiring + board/disembark/schedule
commands."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.features.transit.models import TransitLine, TransitStop
from lorecraft.engine.models.world import Item, Room, WorldClock
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.services.container import ServiceContainer
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.services.mobile_route import MobileRouteService
from lorecraft.engine.services.scheduler import SchedulerService
from lorecraft.features.transit.service import TransitService

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
