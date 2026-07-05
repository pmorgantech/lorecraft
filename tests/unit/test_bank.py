"""Tests for Sprint 28.3: banks (deposit/withdraw/balance, one account,
many branches, banked money is a separate ledger holder)."""

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
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.models.bank import Bank
from lorecraft.models.world import NPC, Room
from lorecraft.models.player import Player, PlayerStats
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.services.container import ServiceContainer
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.game.bank_holders import register as _register_bank

# The "bank_account" holder type used to register as an import side effect; it
# now registers via the bank feature's register(). Call it once here.
_register_bank()

BRANCH_ROOM_ID = "branch"
OTHER_ROOM_ID = "elsewhere"
TELLER_ID = "teller"


def _seed(session: Session) -> None:
    session.add(
        Room(id=BRANCH_ROOM_ID, name="Bank Branch", description="d", map_x=0, map_y=0)
    )
    session.add(
        Room(id=OTHER_ROOM_ID, name="Elsewhere", description="d", map_x=1, map_y=0)
    )
    session.add(
        NPC(
            id=TELLER_ID,
            name="Teller",
            description="d",
            current_room_id=BRANCH_ROOM_ID,
            home_room_id=BRANCH_ROOM_ID,
            dialogue_tree_id="",
        )
    )
    session.add(Bank(id=f"bank:{TELLER_ID}", npc_id=TELLER_ID, name="Saltmarsh Bank"))
    session.commit()


def _build_engine_and_ctx(
    *, room_id: str = BRANCH_ROOM_ID
) -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    _seed(session)
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=room_id,
        respawn_room_id=room_id,
    )
    session.add(player)
    session.add(PlayerStats(player_id=player.id))
    session.commit()

    room = session.get(Room, room_id)
    assert room is not None
    bus = EventBus()
    registry = CommandRegistry()
    services_container = ServiceContainer.build()
    register_all_commands(registry, services_container)

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
def at_branch() -> Iterator[tuple[CommandEngine, GameContext, Session]]:
    cmd_engine, ctx, session = _build_engine_and_ctx(room_id=BRANCH_ROOM_ID)
    yield cmd_engine, ctx, session
    session.close()


@pytest.fixture
def away_from_branch() -> Iterator[tuple[CommandEngine, GameContext, Session]]:
    cmd_engine, ctx, session = _build_engine_and_ctx(room_id=OTHER_ROOM_ID)
    yield cmd_engine, ctx, session
    session.close()


class TestDeposit:
    def test_deposit_moves_coins_to_bank(
        self, at_branch: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = at_branch
        ctx.ledger.credit(session, "player", ctx.player.id, 100)
        session.commit()

        cmd_engine.handle_command("deposit 60", ctx)

        assert ctx.ledger.balance_of(session, "player", ctx.player.id) == 40
        assert any("deposit 60" in m for m in ctx.messages)

    def test_deposit_rejects_insufficient_funds(
        self, at_branch: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = at_branch
        ctx.ledger.credit(session, "player", ctx.player.id, 10)
        session.commit()

        cmd_engine.handle_command("deposit 60", ctx)

        assert any("don't have" in m for m in ctx.messages)
        assert ctx.ledger.balance_of(session, "player", ctx.player.id) == 10

    def test_deposit_requires_a_branch(
        self, away_from_branch: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = away_from_branch
        ctx.ledger.credit(session, "player", ctx.player.id, 100)
        session.commit()

        cmd_engine.handle_command("deposit 60", ctx)

        assert ctx.messages == ["There's no bank here."]
        assert ctx.ledger.balance_of(session, "player", ctx.player.id) == 100


class TestWithdraw:
    def test_withdraw_moves_coins_to_player(
        self, at_branch: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = at_branch
        ctx.ledger.credit(session, "player", ctx.player.id, 100)
        session.commit()
        cmd_engine.handle_command("deposit 100", ctx)

        cmd_engine.handle_command("withdraw 40", ctx)

        assert ctx.ledger.balance_of(session, "player", ctx.player.id) == 40

    def test_withdraw_rejects_insufficient_bank_balance(
        self, at_branch: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = at_branch

        cmd_engine.handle_command("withdraw 40", ctx)

        assert any("doesn't have" in m for m in ctx.messages)

    def test_withdraw_from_a_different_branch_than_deposit(
        self, at_branch: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        """One logical account, many branches."""
        cmd_engine, ctx, session = at_branch
        ctx.ledger.credit(session, "player", ctx.player.id, 100)
        session.commit()
        cmd_engine.handle_command("deposit 100", ctx)

        other_room = session.get(Room, OTHER_ROOM_ID)
        assert other_room is not None
        session.add(
            NPC(
                id="teller2",
                name="Teller Two",
                description="d",
                current_room_id=OTHER_ROOM_ID,
                home_room_id=OTHER_ROOM_ID,
                dialogue_tree_id="",
            )
        )
        session.add(Bank(id="bank:teller2", npc_id="teller2", name="Capital Bank"))
        session.commit()
        ctx.room = other_room

        cmd_engine.handle_command("withdraw 100", ctx)

        assert ctx.ledger.balance_of(session, "player", ctx.player.id) == 100


class TestBalance:
    def test_balance_shows_carried_and_banked(
        self, at_branch: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = at_branch
        ctx.ledger.credit(session, "player", ctx.player.id, 100)
        session.commit()
        cmd_engine.handle_command("deposit 30", ctx)

        cmd_engine.handle_command("balance", ctx)

        assert any("70 coins" in m and "30 coins" in m for m in ctx.messages)

    def test_balance_works_without_visiting_a_branch(
        self, away_from_branch: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = away_from_branch

        cmd_engine.handle_command("balance", ctx)

        assert any("0 coins" in m for m in ctx.messages)
