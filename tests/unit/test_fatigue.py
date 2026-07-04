"""Tests for Sprint 27.1: fatigue drain, rest/sleep/camp, and the low-stamina
skill-check penalty."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.engine import CommandEngine
from lorecraft.game.events import EventBus
from lorecraft.game.fatigue_source import FATIGUE_METER_KEY, FatigueModifierSource
from lorecraft.game.holders import Location
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rng import GameRng
from lorecraft.game.rules import RuleEngine
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.world import Exit, Item, Room
from lorecraft.models.player import Player, PlayerStats
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.effects import EffectService
from lorecraft.services.item_location import ItemLocationService
from lorecraft.services.container import ServiceContainer
from lorecraft.services.ledger import LedgerService
from lorecraft.services.meters import MeterService

START_ROOM_ID = "start"
DEST_ROOM_ID = "dest"


def _seed(session: Session) -> None:
    session.add(
        Room(id=START_ROOM_ID, name="Start Room", description="d", map_x=0, map_y=0)
    )
    session.add(
        Room(id=DEST_ROOM_ID, name="Dest Room", description="d", map_x=1, map_y=0)
    )
    session.add(
        Exit(room_id=START_ROOM_ID, direction="east", target_room_id=DEST_ROOM_ID)
    )
    session.add(
        Exit(room_id=DEST_ROOM_ID, direction="west", target_room_id=START_ROOM_ID)
    )
    session.add(Item(id="anvil", name="anvil", description="Heavy.", weight=90.0))
    session.commit()


def _build_engine_and_ctx() -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    _seed(session)
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=START_ROOM_ID,
        respawn_room_id=START_ROOM_ID,
    )
    session.add(player)
    session.add(PlayerStats(player_id=player.id))
    session.commit()

    room = session.get(Room, START_ROOM_ID)
    assert room is not None
    bus = EventBus()
    registry = CommandRegistry()
    services_container = ServiceContainer.build()
    register_all_commands(registry, services_container)
    services_container.fatigue.register(bus)

    ctx = GameContext(
        player=player,
        room=room,
        clock=None,
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
        manager=ConnectionManager(),
        bus=bus,
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
    return CommandEngine(registry, RuleEngine()), ctx, session


@pytest.fixture
def built() -> Iterator[tuple[CommandEngine, GameContext, Session]]:
    cmd_engine, ctx, session = _build_engine_and_ctx()
    yield cmd_engine, ctx, session
    session.close()


def _fatigue(ctx: GameContext):
    return ctx.meters.get(ctx.session, "player", ctx.player.id, FATIGUE_METER_KEY)


class TestFatigueDrainOnTravel:
    def test_move_drains_fatigue_unburdened(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        before = _fatigue(ctx)
        maximum = before.maximum

        cmd_engine.handle_command("go east", ctx)

        after = _fatigue(ctx)
        assert after.current == maximum - 2.0

    def test_move_drains_more_when_burdened(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        ctx.item_location.spawn("anvil", Location("player", ctx.player.id))
        session.commit()
        maximum = _fatigue(ctx).maximum

        cmd_engine.handle_command("go east", ctx)

        after = _fatigue(ctx)
        assert after.current == maximum - 4.0


class TestRestSleepCamp:
    def test_rest_restores_a_little(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        meter = _fatigue(ctx)
        ctx.meters.adjust(ctx.session, meter, -30.0)

        cmd_engine.handle_command("rest", ctx)

        assert _fatigue(ctx).current == meter.maximum - 10.0
        assert any("less tired" in m for m in ctx.messages)

    def test_camp_restores_more_than_rest(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        meter = _fatigue(ctx)
        ctx.meters.adjust(ctx.session, meter, -60.0)

        cmd_engine.handle_command("camp", ctx)

        assert _fatigue(ctx).current == meter.maximum - 5.0

    def test_sleep_restores_to_full(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        meter = _fatigue(ctx)
        ctx.meters.adjust(ctx.session, meter, -80.0)

        cmd_engine.handle_command("sleep", ctx)

        assert _fatigue(ctx).current == meter.maximum

    def test_already_well_rested(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("rest", ctx)

        assert ctx.messages == ["You are already well-rested."]


class TestFatigueSkillPenalty:
    def test_no_penalty_when_well_rested(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built

        modifiers = FatigueModifierSource().modifiers_for(
            session, "player", ctx.player.id
        )
        assert modifiers == []

    def test_penalty_applied_when_exhausted(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        meter = _fatigue(ctx)
        ctx.meters.set_current(session, meter, meter.maximum * 0.1)

        modifiers = FatigueModifierSource().modifiers_for(
            session, "player", ctx.player.id
        )

        assert modifiers
        assert all(m.key.startswith("skill.") and m.kind == "mult" for m in modifiers)
