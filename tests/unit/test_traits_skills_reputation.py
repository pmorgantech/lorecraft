"""Tests for Sprint 24: trait registry (innate + standard), use-based skill
improvement, and reputation/standing gating."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

import lorecraft.game.standard_traits  # noqa: F401 -- registration side effects
from lorecraft.game.reputation_conditions import register as _register_reputation
import lorecraft.game.traits as traits_module
from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.engine import CommandEngine
from lorecraft.game.events import EventBus
from lorecraft.game.modifiers import resolve_for
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rng import GameRng
from lorecraft.game.rules import RuleEngine
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player, PlayerStats
from lorecraft.models.world import Room
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.effects import EffectService
from lorecraft.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.services.meters import MeterService
from lorecraft.services.reputation import ReputationService
from lorecraft.services.skills import SkillService
from lorecraft.services.traits import TraitService

# Reputation conditions used to register as an import side effect; they now
# register via the reputation feature's register(). Call it once for this
# module's tests (idempotent — safe if another module also registered).
_register_reputation()

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


class TestInnateTraits:
    def test_granted_trait_appears_in_traits_for(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        TraitService().grant(session, ctx.player.id, "keen_eyed")

        names = traits_module.get_registry().traits_for(
            session, "player", ctx.player.id
        )

        assert "keen_eyed" in names

    def test_granted_trait_contributes_modifier(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        TraitService().grant(session, ctx.player.id, "keen_eyed")

        resolved = resolve_for(
            session, "player", ctx.player.id, "skill.perception", base=30
        )

        assert resolved == 40

    def test_revoked_trait_no_longer_contributes(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        service = TraitService()
        service.grant(session, ctx.player.id, "clumsy")
        service.revoke(session, ctx.player.id, "clumsy")

        names = traits_module.get_registry().traits_for(
            session, "player", ctx.player.id
        )

        assert "clumsy" not in names

    def test_grant_is_idempotent(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        service = TraitService()
        service.grant(session, ctx.player.id, "frail")
        service.grant(session, ctx.player.id, "frail")

        stats = session.get(PlayerStats, ctx.player.id)
        assert stats is not None
        assert stats.traits.count("frail") == 1

    def test_traits_command_lists_active_traits(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        TraitService().grant(session, ctx.player.id, "keen_eyed")

        cmd_engine.handle_command("traits", ctx)

        assert any("keen_eyed" in m for m in ctx.messages)

    def test_traits_command_empty(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("traits", ctx)

        assert ctx.messages == ["You have no notable traits."]


class TestSkills:
    def test_get_level_defaults_to_zero(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built

        level = SkillService().get_level(session, ctx.player.id, "perception")

        assert level == 0

    def test_record_use_improves_with_favorable_rng(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        rng = GameRng(seed=1)
        service = SkillService()

        improved = False
        for _ in range(200):
            if service.record_use(session, rng, ctx.player.id, "lockpicking"):
                improved = True
                break

        assert improved
        assert service.get_level(session, ctx.player.id, "lockpicking") == 1

    def test_record_use_caps_at_max_level(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        stats = session.get(PlayerStats, ctx.player.id)
        assert stats is not None
        stats.skills = {"survival": 100}
        session.add(stats)
        session.commit()

        rng = GameRng(seed=1)
        service = SkillService()
        for _ in range(20):
            service.record_use(session, rng, ctx.player.id, "survival")

        assert service.get_level(session, ctx.player.id, "survival") == 100

    def test_skills_command_lists_all_standard_skills(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("skills", ctx)

        assert any("perception" in m for m in ctx.messages)
        assert any("bartering" in m for m in ctx.messages)


class TestReputation:
    def test_standing_defaults_to_zero(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built

        standing = ReputationService().standing_of(
            session, ctx.player.id, "npc", "mira"
        )

        assert standing == 0

    def test_adjust_increases_standing(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        service = ReputationService()

        service.adjust(session, ctx.player.id, "npc", "mira", 15)
        standing = service.standing_of(session, ctx.player.id, "npc", "mira")

        assert standing == 15

    def test_adjust_clamps_to_bounds(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        service = ReputationService()

        service.adjust(session, ctx.player.id, "npc", "mira", 1000)
        standing = service.standing_of(session, ctx.player.id, "npc", "mira")

        assert standing == 100

    def test_reputation_at_least_condition_blocks_below_threshold(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        from lorecraft.game.command_conditions import get_registry

        _cmd_engine, ctx, _session = built
        result = get_registry().evaluate("reputation_at_least:npc:mira:10", ctx)

        assert not result.allowed

    def test_reputation_at_least_condition_passes_above_threshold(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        from lorecraft.game.command_conditions import get_registry

        _cmd_engine, ctx, session = built
        ReputationService().adjust(session, ctx.player.id, "npc", "mira", 20)

        result = get_registry().evaluate("reputation_at_least:npc:mira:10", ctx)

        assert result.allowed

    def test_min_reputation_dialogue_condition(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        from lorecraft.npc.dialogue_conditions import get_registry

        _cmd_engine, ctx, session = built
        ReputationService().adjust(session, ctx.player.id, "npc", "mira", 5)

        satisfied = get_registry().evaluate(
            {"min_reputation": {"target_type": "npc", "target_id": "mira", "min": 10}},
            ctx,
        )

        assert not satisfied

    def test_reputation_command_lists_standings(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        ReputationService().adjust(session, ctx.player.id, "npc", "mira", 15)

        cmd_engine.handle_command("reputation", ctx)

        assert any("mira" in m and "15" in m for m in ctx.messages)

    def test_reputation_command_empty(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("reputation", ctx)

        assert ctx.messages == ["You have no reputation with anyone yet."]
