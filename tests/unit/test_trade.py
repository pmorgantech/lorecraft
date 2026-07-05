"""Tests for Sprint 28.4: player-to-player trade (offer/accept/decline,
atomic escrow swap)."""

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
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.models.world import Item, Room
from lorecraft.models.player import Player, PlayerStats
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.container import ServiceContainer
from lorecraft.services.effects import EffectService
from lorecraft.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.services.meters import MeterService

ROOM_ID = "square"
ALICE_ID = "alice"
BOB_ID = "bob"


def _seed(session: Session) -> None:
    session.add(Room(id=ROOM_ID, name="Square", description="d", map_x=0, map_y=0))
    session.add(Item(id="sword", name="rusty sword", description="d", tradeable=True))
    session.add(
        Item(id="heirloom", name="family heirloom", description="d", bound=True)
    )
    session.add(
        Player(
            id=ALICE_ID,
            username="alice",
            current_room_id=ROOM_ID,
            respawn_room_id=ROOM_ID,
        )
    )
    session.add(PlayerStats(player_id=ALICE_ID))
    session.add(
        Player(
            id=BOB_ID, username="bob", current_room_id=ROOM_ID, respawn_room_id=ROOM_ID
        )
    )
    session.add(PlayerStats(player_id=BOB_ID))
    session.commit()


def _ctx_for(player_id: str, session: Session, bus: EventBus) -> GameContext:
    player = session.get(Player, player_id)
    assert player is not None
    room = session.get(Room, player.current_room_id)
    assert room is not None
    return GameContext(
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


@pytest.fixture
def two_players() -> Iterator[tuple[CommandEngine, Session, EventBus]]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    _seed(session)
    bus = EventBus()
    registry = CommandRegistry()
    register_all_commands(registry, ServiceContainer.build())
    yield CommandEngine(registry, RuleEngine()), session, bus
    session.close()


class TestOfferAndAccept:
    def test_item_for_coins_swap(
        self, two_players: tuple[CommandEngine, Session, EventBus]
    ) -> None:
        cmd_engine, session, bus = two_players
        alice = _ctx_for(ALICE_ID, session, bus)
        alice.item_location.spawn("sword", Location("player", ALICE_ID))
        alice.ledger.credit(session, "player", BOB_ID, 100)
        session.commit()

        cmd_engine.handle_command("offer sword to bob", alice)
        bob = _ctx_for(BOB_ID, session, bus)
        cmd_engine.handle_command("offer 40 coins to alice", bob)
        cmd_engine.handle_command("accept", bob)

        assert bob.stack_repo.quantity_of(Location("player", BOB_ID), "sword") == 1
        assert alice.stack_repo.quantity_of(Location("player", ALICE_ID), "sword") == 0
        assert alice.ledger.balance_of(session, "player", ALICE_ID) == 40
        assert alice.ledger.balance_of(session, "player", BOB_ID) == 60
        assert any("Trade complete" in m for m in bob.messages)

    def test_accept_with_nothing_pledged(
        self, two_players: tuple[CommandEngine, Session, EventBus]
    ) -> None:
        cmd_engine, session, bus = two_players
        alice = _ctx_for(ALICE_ID, session, bus)
        session.commit()

        cmd_engine.handle_command("offer 0 coins to bob", alice)
        cmd_engine.handle_command("accept", alice)

        assert any("nothing pledged" in m for m in alice.messages)

    def test_accept_fails_if_pledge_no_longer_available(
        self, two_players: tuple[CommandEngine, Session, EventBus]
    ) -> None:
        cmd_engine, session, bus = two_players
        alice = _ctx_for(ALICE_ID, session, bus)
        alice.item_location.spawn("sword", Location("player", ALICE_ID))
        session.commit()

        cmd_engine.handle_command("offer sword to bob", alice)
        bob = _ctx_for(BOB_ID, session, bus)
        cmd_engine.handle_command("offer 40 coins to alice", bob)
        # Alice gives the sword away before Bob accepts -- the escrow
        # revalidation inside execute_exchange must catch this.
        stack_id = next(
            s.id
            for s in alice.stack_repo.stacks_for_owner("player", ALICE_ID)
            if s.item_id == "sword"
        )
        assert stack_id is not None
        alice.item_location.destroy(stack_id, 1)
        session.commit()

        cmd_engine.handle_command("accept", bob)

        assert any("fell through" in m for m in bob.messages)

    def test_offer_rejects_bound_item(
        self, two_players: tuple[CommandEngine, Session, EventBus]
    ) -> None:
        cmd_engine, session, bus = two_players
        alice = _ctx_for(ALICE_ID, session, bus)
        alice.item_location.spawn("heirloom", Location("player", ALICE_ID))
        session.commit()

        cmd_engine.handle_command("offer heirloom to bob", alice)

        assert any("can't trade" in m for m in alice.messages)

    def test_offer_rejects_unknown_recipient(
        self, two_players: tuple[CommandEngine, Session, EventBus]
    ) -> None:
        cmd_engine, session, bus = two_players
        alice = _ctx_for(ALICE_ID, session, bus)

        cmd_engine.handle_command("offer sword to nobody", alice)

        assert any("no nobody here" in m for m in alice.messages)


class TestDecline:
    def test_decline_clears_pending_offer(
        self, two_players: tuple[CommandEngine, Session, EventBus]
    ) -> None:
        cmd_engine, session, bus = two_players
        alice = _ctx_for(ALICE_ID, session, bus)
        alice.ledger.credit(session, "player", ALICE_ID, 100)
        session.commit()

        cmd_engine.handle_command("offer 40 coins to bob", alice)
        cmd_engine.handle_command("decline", alice)
        cmd_engine.handle_command("accept", alice)

        assert any("no pending trade" in m for m in alice.messages)
        assert alice.ledger.balance_of(session, "player", ALICE_ID) == 100

    def test_decline_with_no_offer(
        self, two_players: tuple[CommandEngine, Session, EventBus]
    ) -> None:
        cmd_engine, session, bus = two_players
        alice = _ctx_for(ALICE_ID, session, bus)

        cmd_engine.handle_command("decline", alice)

        assert any("no pending trade" in m for m in alice.messages)
