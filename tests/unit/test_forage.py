"""The `forage` active ability: flag-gating + survival-check yield (Sprint 74.5)."""

from __future__ import annotations

import pytest
from sqlmodel import Session, create_engine

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
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Item, Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.exploration.commands import register_exploration_commands
from lorecraft.features.exploration.forage import (
    ForageRegistry,
    ForageService,
    validate_forage_document,
)

ROOM_ID = "meadow"


def _forage_registry() -> ForageRegistry:
    registry = ForageRegistry()
    registry.load_document(
        validate_forage_document(
            {"entries": [{"terrain": "*", "items": ["wild_berries"]}]}
        )
    )
    return registry


def _build(
    *, seed: int, has_flag: bool, indoor: bool = False, survival: int = 90
) -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    session.add(
        Room(
            id=ROOM_ID,
            name="Meadow",
            description="d",
            map_x=0,
            map_y=0,
            terrain="normal",
            indoor=indoor,
        )
    )
    session.add(
        Item(id="wild_berries", name="Wild Berries", description="d", category="food")
    )
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=ROOM_ID,
        respawn_room_id=ROOM_ID,
        flags={"ability.forage": True} if has_flag else {},
    )
    session.add(player)
    session.add(
        PlayerStats(player_id=player.id, discipline_ranks={"survival": survival})
    )
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
        rng=GameRng(seed=seed),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id=player.id, correlation_id="s1"),
        session_id="s1",
    )
    registry = CommandRegistry()
    register_exploration_commands(registry, forage=ForageService(_forage_registry()))
    return CommandEngine(registry, RuleEngine()), ctx, session


def _carries(ctx: GameContext, item_id: str) -> bool:
    return ctx.stack_repo.quantity_of(Location("player", ctx.player.id), item_id) > 0


def test_forage_hidden_without_ability_flag() -> None:
    cmd_engine, ctx, session = _build(seed=1, has_flag=False)
    try:
        cmd_engine.handle_command("forage", ctx)
        # Gated off: the verb is unavailable and yields the gate's refusal, never
        # a forage result.
        assert not any("You forage and find" in m for m in ctx.messages)
        assert ctx.messages == ["You can't do that yet."]
    finally:
        session.close()


def test_forage_command_listed_in_help_only_with_flag() -> None:
    registry = CommandRegistry()
    register_exploration_commands(registry, forage=ForageService(_forage_registry()))
    definition = registry.get("forage")
    assert definition is not None
    # The gate is on the command so the help-availability filter hides it until
    # the flag is set.
    assert "actor_has_flag:ability.forage" in definition.conditions


def test_forage_success_yields_a_consumable() -> None:
    for seed in range(50):
        cmd_engine, ctx, session = _build(seed=seed, has_flag=True, survival=95)
        try:
            cmd_engine.handle_command("forage", ctx)
            if any("You forage and find" in m for m in ctx.messages):
                assert _carries(ctx, "wild_berries")
                return
        finally:
            session.close()
    pytest.fail("no seed produced a successful forage in 50 tries")


def test_forage_failure_yields_nothing() -> None:
    for seed in range(50):
        cmd_engine, ctx, session = _build(seed=seed, has_flag=True, survival=0)
        try:
            cmd_engine.handle_command("forage", ctx)
            if any("turn up nothing edible" in m for m in ctx.messages):
                assert not _carries(ctx, "wild_berries")
                return
        finally:
            session.close()
    pytest.fail("no seed produced a failed forage in 50 tries")


def test_forage_refused_indoors() -> None:
    cmd_engine, ctx, session = _build(seed=1, has_flag=True, indoor=True, survival=95)
    try:
        cmd_engine.handle_command("forage", ctx)
        assert any("nothing to forage indoors" in m for m in ctx.messages)
        assert not _carries(ctx, "wild_berries")
    finally:
        session.close()
