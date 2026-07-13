"""Tests for Sprint 24: trait registry (innate + standard), use-based skill
improvement, and reputation/standing gating."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.features.reputation.conditions import register as _register_reputation
from lorecraft.features.traits.standard import register as _register_standard_traits
from lorecraft.features.traits.sources import register as _register_trait_sources
from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.disciplines.abilities import (
    get_discipline_registry,
    load_disciplines_yaml,
)
from lorecraft.features.disciplines.service import ProficiencyService

# Traits + reputation used to register as import side effects; they now register
# via their feature register()s. Call them once for this module's tests
# (idempotent — safe if another module also registered).
_register_trait_sources()
_register_standard_traits()
_register_reputation()
# Discipline ranks replace the old flat skills; the proficiency/command tests
# below need the seed disciplines loaded into the in-memory registry.
get_discipline_registry().load_document(
    load_disciplines_yaml("world_content/disciplines.yaml")
)

ROOM_ID = "room-1"


def _build_engine_and_ctx() -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    session.add(Room(id=ROOM_ID, name="Room One", description="d", map_x=0, map_y=0))
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=ROOM_ID,
        respawn_room_id=ROOM_ID,
    )
    session.add(player)
    session.add(PlayerStats(player_id=player.id))
    session.commit()

    room = session.get(Room, ROOM_ID)
    assert room is not None
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
        rng=GameRng(seed=42),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
    registry = CommandRegistry()
    register_all_commands(registry)
    return CommandEngine(registry, RuleEngine()), ctx, session


@pytest.fixture
def built() -> Iterator[tuple[CommandEngine, GameContext, Session]]:
    cmd_engine, ctx, session = _build_engine_and_ctx()
    yield cmd_engine, ctx, session
    session.close()


class TestProficiency:
    def test_get_rank_defaults_to_zero(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built

        rank = ProficiencyService().get_rank(session, ctx.player.id, "subterfuge")

        assert rank == 0

    def test_record_use_improves_with_favorable_rng(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        rng = GameRng(seed=1)
        service = ProficiencyService()

        improved = False
        for _ in range(200):
            if service.record_use(session, rng, ctx.player.id, "subterfuge"):
                improved = True
                break

        assert improved
        assert service.get_rank(session, ctx.player.id, "subterfuge") == 1

    def test_record_use_caps_at_max_rank(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        stats = session.get(PlayerStats, ctx.player.id)
        assert stats is not None
        stats.discipline_ranks = {"survival": 100}
        session.add(stats)
        session.commit()

        rng = GameRng(seed=1)
        service = ProficiencyService()
        for _ in range(20):
            service.record_use(session, rng, ctx.player.id, "survival")

        assert service.get_rank(session, ctx.player.id, "survival") == 100

    def test_record_use_unknown_discipline_never_grows(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        service = ProficiencyService()
        grew = service.record_use(session, GameRng(seed=1), ctx.player.id, "nope")
        assert grew is False

    def test_disciplines_command_lists_seed_disciplines(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("disciplines", ctx)

        assert any("Survival" in m for m in ctx.messages)
        assert any("Subterfuge" in m for m in ctx.messages)
