"""Tests for Sprint 27.1-27.2: fatigue drain, rest/sleep/camp, the low-stamina
skill-check penalty, sleep's clock-advance/safe-vs-unsafe risk, and warmth."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.features.fatigue.source import FATIGUE_METER_KEY, FatigueModifierSource
from lorecraft.engine.game.holders import Location
from lorecraft.features.items.effects import compile_item_modifiers
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.features.warmth.rules import resolve_warmth
from lorecraft.engine.models.world import Exit, Item, Room, WorldClock
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.services.container import ServiceContainer
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.equipment.sources import register as _register_equipment_source
from lorecraft.features.fatigue.source import register as _register_fatigue

# The "fatigue" meter + equipment sources used to register as import side
# effects (the fatigue meter via this module's `from fatigue_source import ...`).
# They now register via the fatigue/equipment feature register()s.
_register_fatigue()
_register_equipment_source()

START_ROOM_ID = "start"
DEST_ROOM_ID = "dest"


def _seed(session: Session) -> None:
    session.add(
        Room(
            id=START_ROOM_ID,
            name="Start Room",
            description="d",
            map_x=0,
            map_y=0,
            safe_rest=True,
        )
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
    session.add(
        Item(
            id="cloak",
            name="warm cloak",
            description="A heavy wool cloak.",
            effects=[{"type": "warmth_bonus", "amount": 25}],
        )
    )
    session.add(
        WorldClock(
            id=1,
            game_epoch=8 * 3600.0,
            real_epoch=0.0,
            current_day=1,
            weather="clear",
        )
    )
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

    def test_sleep_in_safe_room_restores_to_full_and_advances_clock(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        meter = _fatigue(ctx)
        ctx.meters.adjust(ctx.session, meter, -80.0)
        assert ctx.clock is not None
        assert ctx.room.safe_rest is True

        cmd_engine.handle_command("sleep", ctx)

        assert _fatigue(ctx).current == meter.maximum
        assert ctx.clock.current_hour == 16  # 08:00 + 8h

    def test_already_well_rested(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("rest", ctx)

        assert ctx.messages == ["You are already well-rested."]


class TestSleepSafetyAndDream:
    def test_unsafe_sleep_may_succeed_or_be_interrupted(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        dest = session.get(Room, DEST_ROOM_ID)
        assert dest is not None
        ctx.room = dest
        meter = _fatigue(ctx)
        ctx.meters.adjust(ctx.session, meter, -80.0)

        cmd_engine.handle_command("sleep", ctx)

        assert any(
            "full night's rest" in m or "fitful and interrupted" in m
            for m in ctx.messages
        )
        if any("fitful" in m for m in ctx.messages):
            assert _fatigue(ctx).current == meter.maximum - 80.0 + 20.0
            assert ctx.clock is not None and ctx.clock.current_hour == 11  # +3h
        else:
            assert _fatigue(ctx).current == meter.maximum
            assert ctx.clock is not None and ctx.clock.current_hour == 16  # +8h

    def test_dream_after_safe_sleep_references_lore_flag(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        ctx.player.flags = {**ctx.player.flags, "lore:ancient_ruins": True}

        cmd_engine.handle_command("sleep", ctx)

        assert any("ancient ruins" in m for m in ctx.messages)

    def test_dream_after_safe_sleep_generic_without_lore(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("sleep", ctx)

        assert any("You dream of" in m for m in ctx.messages)


class TestWarmth:
    def test_resolve_warmth_from_equipped_cloak(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        assert resolve_warmth(session, ctx.player.id) == 0.0

        ctx.item_location.spawn("cloak", Location("player", ctx.player.id))
        stack = next(
            s
            for s in ctx.stack_repo.stacks_for_owner("player", ctx.player.id)
            if s.item_id == "cloak"
        )
        stack.slot = "back"
        session.add(stack)
        session.commit()

        assert resolve_warmth(session, ctx.player.id) == 25.0

    def test_compile_item_modifiers_handles_warmth_bonus(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        cloak = ctx.item_repo.get("cloak")
        assert cloak is not None

        modifiers = compile_item_modifiers(cloak)

        assert any(
            m.key == "warmth" and m.kind == "add" and m.amount == 25.0
            for m in modifiers
        )


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
