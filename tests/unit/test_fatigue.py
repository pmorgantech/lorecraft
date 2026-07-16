"""Tests for Sprint 27.1-27.2: fatigue drain, rest/sleep/camp, the low-stamina
skill-check penalty, sleep's clock-advance/safe-vs-unsafe risk, and warmth."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.meters import MeterDef
from lorecraft.engine.game.meters import get_registry as get_meter_registry
from lorecraft.features.disciplines.abilities import (
    get_discipline_registry,
    load_disciplines_yaml,
)
from lorecraft.features.fatigue.source import FATIGUE_METER_KEY, FatigueModifierSource
from lorecraft.engine.game.holders import Location
from lorecraft.features.items.effects import compile_item_modifiers
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.features.warmth.rules import resolve_warmth
from lorecraft.engine.clock.world_clock import ClockEventContext
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
get_meter_registry().register(MeterDef(key="hp", base_maximum=lambda et, eid, s: 100.0))
get_discipline_registry().load_document(
    load_disciplines_yaml("world_content/disciplines.yaml")
)

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


def _session_engine(session: Session) -> Engine:
    bind = session.get_bind()
    assert isinstance(bind, Engine)
    return bind


def _fatigue(ctx: GameContext):
    return ctx.meters.get(ctx.session, "player", ctx.player.id, FATIGUE_METER_KEY)


def _hp(ctx: GameContext):
    return ctx.meters.get(ctx.session, "player", ctx.player.id, "hp")


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
    def test_rest_enters_rest_mode_without_instant_restore(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        meter = _fatigue(ctx)
        ctx.meters.adjust(ctx.session, meter, -30.0)

        cmd_engine.handle_command("rest", ctx)

        assert _fatigue(ctx).current == meter.maximum - 30.0
        assert ctx.player.flags["condition:resting"] is True
        assert any("steady rest" in m for m in ctx.messages)

    def test_camp_restores_more_than_rest(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        meter = _fatigue(ctx)
        ctx.meters.adjust(ctx.session, meter, -60.0)

        cmd_engine.handle_command("camp", ctx)

        assert _fatigue(ctx).current == meter.maximum - 5.0

    def test_sleep_in_safe_room_sets_sleep_state(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        meter = _fatigue(ctx)
        ctx.meters.adjust(ctx.session, meter, -80.0)
        assert ctx.clock is not None
        assert ctx.room.safe_rest is True

        cmd_engine.handle_command("sleep 8", ctx)

        assert _fatigue(ctx).current == meter.maximum - 80.0
        assert ctx.player.flags["condition:sleeping_until"] == (
            ctx.clock.game_epoch + 8 * 3600.0
        )

    def test_rest_can_start_when_well_rested(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("rest", ctx)

        assert ctx.player.flags["condition:resting"] is True
        assert ctx.messages == [
            "You settle into a steady rest. Stand when you're ready to move again."
        ]

    def test_rest_blocks_movement_until_standing(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("rest", ctx)
        cmd_engine.handle_command("go east", ctx)
        cmd_engine.handle_command("stand", ctx)
        cmd_engine.handle_command("go east", ctx)

        assert any("steady rest" in m for m in ctx.messages)
        assert any("Stand up first" in m for m in ctx.messages)
        assert ctx.player.current_room_id == DEST_ROOM_ID

    def test_sleep_requires_hours_and_blocks_commands(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        assert ctx.clock is not None

        cmd_engine.handle_command("sleep", ctx)
        cmd_engine.handle_command("sleep 2", ctx)
        cmd_engine.handle_command("look", ctx)

        assert any("Sleep for how many hours" in m for m in ctx.messages)
        assert any("asleep" in m for m in ctx.messages)

    def test_sleep_recovers_faster_than_rest_on_time_advance(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        meter = _fatigue(ctx)
        ctx.meters.adjust(ctx.session, meter, -80.0)
        cmd_engine.handle_command("rest", ctx)
        session.commit()
        ctx.bus.emit(
            Event(
                GameEvent.TIME_ADVANCED,
                {"previous_epoch": 0.0, "current_epoch": 3600.0},
            ),
            ClockEventContext(game_engine=_session_engine(session), bus=ctx.bus),
        )
        rest_current = _fatigue(ctx).current

        ctx.meters.set_current(session, _fatigue(ctx), meter.maximum - 80.0)
        ctx.player.flags = {}
        session.add(ctx.player)
        session.commit()
        cmd_engine.handle_command("sleep 2", ctx)
        session.commit()
        ctx.bus.emit(
            Event(
                GameEvent.TIME_ADVANCED,
                {"previous_epoch": 0.0, "current_epoch": 3600.0},
            ),
            ClockEventContext(game_engine=_session_engine(session), bus=ctx.bus),
        )

        session.expire_all()
        assert _fatigue(ctx).current > rest_current

    def test_hp_recovers_over_time_faster_with_rest_and_sleep(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        hp = _hp(ctx)
        ctx.meters.set_current(session, hp, 50.0)
        session.commit()
        assert ctx.clock is not None

        ctx.bus.emit(
            Event(
                GameEvent.TIME_ADVANCED,
                {
                    "previous_epoch": ctx.clock.game_epoch,
                    "current_epoch": ctx.clock.game_epoch + 3600.0,
                },
            ),
            ClockEventContext(_session_engine(session), ctx.bus),
        )
        normal_hp = _hp(ctx).current

        ctx.meters.set_current(session, _hp(ctx), 50.0)
        session.commit()
        cmd_engine.handle_command("rest", ctx)
        session.commit()
        ctx.bus.emit(
            Event(
                GameEvent.TIME_ADVANCED,
                {
                    "previous_epoch": ctx.clock.game_epoch,
                    "current_epoch": ctx.clock.game_epoch + 3600.0,
                },
            ),
            ClockEventContext(_session_engine(session), ctx.bus),
        )
        rest_hp = _hp(ctx).current

        ctx.meters.set_current(session, _hp(ctx), 50.0)
        session.commit()
        cmd_engine.handle_command("stand", ctx)
        cmd_engine.handle_command("sleep 2", ctx)
        session.commit()
        ctx.bus.emit(
            Event(
                GameEvent.TIME_ADVANCED,
                {
                    "previous_epoch": ctx.clock.game_epoch,
                    "current_epoch": ctx.clock.game_epoch + 3600.0,
                },
            ),
            ClockEventContext(_session_engine(session), ctx.bus),
        )
        sleep_hp = _hp(ctx).current

        assert normal_hp == 52.0
        assert rest_hp == 58.0
        assert sleep_hp == 70.0

    def test_room_vital_recovery_multiplier_beats_sleep(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        ctx.room.flags = {"vital_recovery_multiplier": 3.0}
        ctx.meters.set_current(session, _hp(ctx), 10.0)
        ctx.meters.set_current(session, _fatigue(ctx), 10.0)
        session.add(ctx.room)
        session.commit()
        assert ctx.clock is not None

        ctx.bus.emit(
            Event(
                GameEvent.TIME_ADVANCED,
                {
                    "previous_epoch": ctx.clock.game_epoch,
                    "current_epoch": ctx.clock.game_epoch + 3600.0,
                },
            ),
            ClockEventContext(_session_engine(session), ctx.bus),
        )

        assert _hp(ctx).current == 70.0
        assert _fatigue(ctx).current == 52.0


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

        cmd_engine.handle_command("sleep 8", ctx)

        assert any("sleep" in m or "fitful" in m for m in ctx.messages)
        assert _fatigue(ctx).current == meter.maximum - 80.0
        assert "condition:sleeping_until" in ctx.player.flags

    def test_dream_after_safe_sleep_references_lore_flag(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        ctx.player.flags = {**ctx.player.flags, "lore:ancient_ruins": True}

        cmd_engine.handle_command("sleep 8", ctx)

        assert any("ancient ruins" in m for m in ctx.messages)

    def test_dream_after_safe_sleep_generic_without_lore(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("sleep 8", ctx)

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
