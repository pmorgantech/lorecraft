"""The `sense` and `pick` active abilities (Sprint 74.6): flag-gating + skill rolls."""

from __future__ import annotations

import pytest
from sqlmodel import Session, create_engine

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
from lorecraft.engine.models.world import Exit, Room
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
from lorecraft.features.movement.commands import register_movement_commands

START = "start"
DEST = "dest"


def _build(
    *,
    seed: int,
    flags: dict[str, bool],
    hidden_exit: bool = False,
    locked_exit: bool = False,
    perception: int = 90,
    lockpicking: int = 90,
) -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    session.add(Room(id=START, name="Start", description="d", map_x=0, map_y=0))
    session.add(Room(id=DEST, name="Dest", description="d", map_x=1, map_y=0))
    if hidden_exit:
        session.add(
            Exit(room_id=START, direction="north", target_room_id=DEST, hidden=True)
        )
    if locked_exit:
        session.add(
            Exit(room_id=START, direction="east", target_room_id=DEST, locked=True)
        )
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=START,
        respawn_room_id=START,
        flags=dict(flags),
    )
    session.add(player)
    session.add(
        PlayerStats(
            player_id=player.id,
            skills={"perception": perception, "lockpicking": lockpicking},
        )
    )
    session.commit()

    room = session.get(Room, START)
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
    register_exploration_commands(registry)
    register_movement_commands(registry)
    return CommandEngine(registry, RuleEngine()), ctx, session


# --- sense ---


def test_sense_hidden_without_flag() -> None:
    cmd_engine, ctx, session = _build(seed=1, flags={}, hidden_exit=True)
    try:
        cmd_engine.handle_command("sense", ctx)
        assert ctx.messages == ["You can't do that yet."]
    finally:
        session.close()


def test_sense_reveals_hidden_passage_on_success() -> None:
    for seed in range(50):
        cmd_engine, ctx, session = _build(
            seed=seed,
            flags={"ability.keen_senses": True},
            hidden_exit=True,
            perception=95,
        )
        try:
            cmd_engine.handle_command("sense", ctx)
            if any("hidden passage to the north" in m for m in ctx.messages):
                return
        finally:
            session.close()
    pytest.fail("no seed produced a successful sense in 50 tries")


def test_sense_failure_reports_nothing() -> None:
    for seed in range(50):
        cmd_engine, ctx, session = _build(
            seed=seed,
            flags={"ability.keen_senses": True},
            hidden_exit=True,
            perception=0,
        )
        try:
            cmd_engine.handle_command("sense", ctx)
            if any("notice nothing unusual" in m for m in ctx.messages):
                assert not any("hidden passage" in m for m in ctx.messages)
                return
        finally:
            session.close()
    pytest.fail("no seed produced a failed sense in 50 tries")


# --- pick ---


def test_pick_hidden_without_flag() -> None:
    cmd_engine, ctx, session = _build(seed=1, flags={}, locked_exit=True)
    try:
        cmd_engine.handle_command("pick east", ctx)
        assert ctx.messages == ["You can't do that yet."]
    finally:
        session.close()


def test_pick_opens_locked_exit_on_success() -> None:
    for seed in range(50):
        cmd_engine, ctx, session = _build(
            seed=seed,
            flags={"ability.pick_locks": True},
            locked_exit=True,
            lockpicking=95,
        )
        try:
            cmd_engine.handle_command("pick east", ctx)
            if any("The way east is now open" in m for m in ctx.messages):
                exit_ = ctx.room_repo.exit(START, "east")
                assert exit_ is not None and exit_.locked is False
                return
        finally:
            session.close()
    pytest.fail("no seed produced a successful pick in 50 tries")


def test_pick_failure_leaves_exit_locked() -> None:
    for seed in range(50):
        cmd_engine, ctx, session = _build(
            seed=seed,
            flags={"ability.pick_locks": True},
            locked_exit=True,
            lockpicking=0,
        )
        try:
            cmd_engine.handle_command("pick east", ctx)
            if any("it holds" in m for m in ctx.messages):
                exit_ = ctx.room_repo.exit(START, "east")
                assert exit_ is not None and exit_.locked is True
                return
        finally:
            session.close()
    pytest.fail("no seed produced a failed pick in 50 tries")


def test_pick_refused_on_unlocked_exit() -> None:
    cmd_engine, ctx, session = _build(
        seed=1, flags={"ability.pick_locks": True}, hidden_exit=True
    )
    try:
        # north exists but is not locked.
        cmd_engine.handle_command("pick north", ctx)
        assert any("isn't locked" in m for m in ctx.messages)
    finally:
        session.close()
