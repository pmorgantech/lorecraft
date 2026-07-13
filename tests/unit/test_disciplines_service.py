"""AbilityService acquisition + train/abilities command output (Sprint 78.9).

Exercises the Tier 2 skill-point sink end to end against the real seed content:
check_acquisition-driven purchase (cost/prereq/rank gates), the owned/available/
locked partition, and the two commands' single cohesive ctx.say() output.
"""

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
    get_ability_registry,
    get_discipline_registry,
    load_abilities_yaml,
    load_disciplines_yaml,
)
from lorecraft.features.disciplines.service import AbilityService

# Load the real seed content into the global registries the services default to.
get_discipline_registry().load_document(
    load_disciplines_yaml("world_content/disciplines.yaml")
)
get_ability_registry().load_document(
    load_abilities_yaml("world_content/abilities.yaml")
)

ROOM_ID = "room-1"


@pytest.fixture
def built() -> Iterator[tuple[CommandEngine, GameContext, Session]]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    session.add(Room(id=ROOM_ID, name="Room", description="d", map_x=0, map_y=0))
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=ROOM_ID,
        respawn_room_id=ROOM_ID,
    )
    session.add(player)
    session.add(PlayerStats(player_id=player.id, skill_points=5))
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
        rng=GameRng(seed=1),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id=player.id, correlation_id="s"),
        session_id="s",
    )
    registry = CommandRegistry()
    register_all_commands(registry)
    yield CommandEngine(registry, RuleEngine()), ctx, session
    session.close()


def _owned(ctx: GameContext) -> list[str]:
    stats = ctx.player_repo.stats(ctx.player.id)
    return list(stats.unlocked_nodes) if stats is not None else []


class TestAbilityService:
    def test_purchase_success_dual_writes_and_spends(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd, ctx, _session = built
        service = AbilityService()

        result = service.purchase(ctx, "forage")

        assert result.ok
        assert "forage" in _owned(ctx)
        assert ctx.player.flags.get("ability.forage") is True
        stats = ctx.player_repo.stats(ctx.player.id)
        assert stats is not None and stats.skill_points == 4  # 5 - cost(1)

    def test_purchase_unknown_ability_is_rejected(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd, ctx, _session = built
        result = AbilityService().purchase(ctx, "does_not_exist")
        assert not result.ok
        assert "no ability" in result.reason.lower()

    def test_purchase_already_known_is_rejected(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd, ctx, _session = built
        service = AbilityService()
        service.purchase(ctx, "forage")
        result = service.purchase(ctx, "forage")
        assert not result.ok
        assert "already know" in result.reason.lower()

    def test_purchase_missing_prerequisite_is_rejected(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd, ctx, _session = built
        # sharp_eyes requires keen_senses.
        result = AbilityService().purchase(ctx, "sharp_eyes")
        assert not result.ok
        assert "keen senses" in result.reason.lower()

    def test_purchase_insufficient_points_is_rejected(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd, ctx, _session = built
        stats = ctx.player_repo.stats(ctx.player.id)
        assert stats is not None
        stats.skill_points = 0
        ctx.player_repo.save_stats(stats)
        result = AbilityService().purchase(ctx, "forage")
        assert not result.ok
        assert "skill point" in result.reason.lower()

    def test_available_and_locked_partition(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd, ctx, _session = built
        service = AbilityService()
        available = {a.id for a in service.available_nodes(ctx)}
        locked = {a.id for a in service.locked_nodes(ctx)}
        # No overlap; sharp_eyes is locked (needs keen_senses); forage is available.
        assert available.isdisjoint(locked)
        assert "forage" in available
        assert "sharp_eyes" in locked


class TestCommands:
    def test_train_no_arg_lists_trainable_in_one_message(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd, ctx, _session = built
        cmd.handle_command("train", ctx)
        # Exactly one cohesive say(), listing an available ability.
        assert len(ctx.messages) == 1
        assert "You can train" in ctx.messages[0]
        assert "Forage" in ctx.messages[0]

    def test_train_ability_purchases_and_reports_once(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd, ctx, _session = built
        cmd.handle_command("train forage", ctx)
        assert "forage" in _owned(ctx)
        assert any("You train Forage" in m for m in ctx.messages)

    def test_abilities_command_single_message(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd, ctx, _session = built
        AbilityService().purchase(ctx, "forage")
        cmd.handle_command("abilities", ctx)
        assert len(ctx.messages) == 1
        assert "Forage" in ctx.messages[0]
