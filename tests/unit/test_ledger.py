"""Unit tests for LedgerService (engine_core.md §3.7)."""

from __future__ import annotations

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.errors import ConflictError, NotFoundError, ValidationError
from lorecraft.engine.game.holders import Location
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Item, Room
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import ExchangeLeg, LedgerService


def _make_session() -> Session:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return Session(engine)


def _seed_world(session: Session) -> None:
    session.add(
        Player(id="alice", username="alice", current_room_id="r", respawn_room_id="r")
    )
    session.add(
        Player(id="bob", username="bob", current_room_id="r", respawn_room_id="r")
    )
    session.add(Room(id="r", name="Room", description="d", map_x=0, map_y=0))
    session.add(Item(id="coin_pouch", name="Coin Pouch", description="Jingling."))
    session.commit()


@pytest.fixture
def session():
    s = _make_session()
    _seed_world(s)
    yield s
    s.close()


class TestBalanceOfAndCredit:
    def test_balance_of_unknown_holder_is_zero(self, session: Session) -> None:
        service = LedgerService()
        assert service.balance_of(session, "player", "alice") == 0

    def test_credit_creates_balance_lazily(self, session: Session) -> None:
        service = LedgerService()
        service.credit(session, "player", "alice", 100)
        assert service.balance_of(session, "player", "alice") == 100

    def test_credit_accumulates(self, session: Session) -> None:
        service = LedgerService()
        service.credit(session, "player", "alice", 100)
        service.credit(session, "player", "alice", 50)
        assert service.balance_of(session, "player", "alice") == 150

    def test_credit_rejects_negative_amount(self, session: Session) -> None:
        service = LedgerService()
        with pytest.raises(ValidationError):
            service.credit(session, "player", "alice", -10)


class TestExecuteExchangeCoins:
    def test_moves_coins_between_holders(self, session: Session) -> None:
        service = LedgerService()
        service.credit(session, "player", "alice", 100)

        receipt = service.execute_exchange(
            session,
            [
                ExchangeLeg(
                    give_from=Location("player", "alice"),
                    give_to=Location("player", "bob"),
                    coins=30,
                )
            ],
        )

        assert service.balance_of(session, "player", "alice") == 70
        assert service.balance_of(session, "player", "bob") == 30
        assert receipt.total_coins_moved == 30
        assert receipt.leg_count == 1

    def test_rejects_insufficient_balance_and_applies_nothing(
        self, session: Session
    ) -> None:
        service = LedgerService()
        service.credit(session, "player", "alice", 10)

        with pytest.raises(ConflictError):
            service.execute_exchange(
                session,
                [
                    ExchangeLeg(
                        give_from=Location("player", "alice"),
                        give_to=Location("player", "bob"),
                        coins=100,
                    )
                ],
            )

        assert service.balance_of(session, "player", "alice") == 10
        assert service.balance_of(session, "player", "bob") == 0

    def test_rejects_unknown_destination_holder(self, session: Session) -> None:
        service = LedgerService()
        service.credit(session, "player", "alice", 100)

        with pytest.raises(NotFoundError):
            service.execute_exchange(
                session,
                [
                    ExchangeLeg(
                        give_from=Location("player", "alice"),
                        give_to=Location("player", "no-such-player"),
                        coins=10,
                    )
                ],
            )

        assert service.balance_of(session, "player", "alice") == 100

    def test_rejects_negative_coins(self, session: Session) -> None:
        service = LedgerService()
        with pytest.raises(ValidationError):
            service.execute_exchange(
                session,
                [
                    ExchangeLeg(
                        give_from=Location("player", "alice"),
                        give_to=Location("player", "bob"),
                        coins=-5,
                    )
                ],
            )


class TestExecuteExchangeStacks:
    def test_moves_stacks_between_holders(self, session: Session) -> None:
        item_location = ItemLocationService(session)
        stack = item_location.spawn("coin_pouch", Location("player", "alice"), 3)[0]
        assert stack.id is not None

        service = LedgerService()
        service.execute_exchange(
            session,
            [
                ExchangeLeg(
                    give_from=Location("player", "alice"),
                    give_to=Location("player", "bob"),
                    stacks=((stack.id, 2),),
                )
            ],
        )

        alice_stacks = StackRepo(session).stacks_for_owner("player", "alice")
        bob_stacks = StackRepo(session).stacks_for_owner("player", "bob")
        assert sum(s.quantity for s in alice_stacks) == 1
        assert sum(s.quantity for s in bob_stacks) == 2

    def test_rejects_stack_not_at_declared_location(self, session: Session) -> None:
        item_location = ItemLocationService(session)
        stack = item_location.spawn("coin_pouch", Location("player", "bob"), 1)[0]
        assert stack.id is not None

        service = LedgerService()
        with pytest.raises(ConflictError):
            # Leg claims the stack is at alice's, but it's actually at bob's.
            service.execute_exchange(
                session,
                [
                    ExchangeLeg(
                        give_from=Location("player", "alice"),
                        give_to=Location("player", "bob"),
                        stacks=((stack.id, 1),),
                    )
                ],
            )

    def test_rejects_insufficient_stack_quantity(self, session: Session) -> None:
        item_location = ItemLocationService(session)
        stack = item_location.spawn("coin_pouch", Location("player", "alice"), 1)[0]
        assert stack.id is not None

        service = LedgerService()
        with pytest.raises(ConflictError):
            service.execute_exchange(
                session,
                [
                    ExchangeLeg(
                        give_from=Location("player", "alice"),
                        give_to=Location("player", "bob"),
                        stacks=((stack.id, 5),),
                    )
                ],
            )

    def test_rejects_unknown_stack(self, session: Session) -> None:
        service = LedgerService()
        with pytest.raises(NotFoundError):
            service.execute_exchange(
                session,
                [
                    ExchangeLeg(
                        give_from=Location("player", "alice"),
                        give_to=Location("player", "bob"),
                        stacks=((999999, 1),),
                    )
                ],
            )


class TestExecuteExchangeMultiLegConservation:
    def test_two_way_trade_conserves_totals(self, session: Session) -> None:
        """P2P trade shape: accept() is one execute_exchange with both directions
        as legs — alice gives coins for bob's item, atomically."""
        item_location = ItemLocationService(session)
        stack = item_location.spawn("coin_pouch", Location("player", "bob"), 1)[0]
        assert stack.id is not None
        service = LedgerService()
        service.credit(session, "player", "alice", 50)

        total_coins_before = service.balance_of(
            session, "player", "alice"
        ) + service.balance_of(session, "player", "bob")

        service.execute_exchange(
            session,
            [
                ExchangeLeg(
                    give_from=Location("player", "alice"),
                    give_to=Location("player", "bob"),
                    coins=20,
                ),
                ExchangeLeg(
                    give_from=Location("player", "bob"),
                    give_to=Location("player", "alice"),
                    stacks=((stack.id, 1),),
                ),
            ],
        )

        total_coins_after = service.balance_of(
            session, "player", "alice"
        ) + service.balance_of(session, "player", "bob")
        assert total_coins_after == total_coins_before
        assert service.balance_of(session, "player", "alice") == 30
        assert service.balance_of(session, "player", "bob") == 20
        assert StackRepo(session).stacks_for_owner("player", "alice")[0].quantity == 1

    def test_failing_leg_applies_nothing_from_any_leg(self, session: Session) -> None:
        item_location = ItemLocationService(session)
        stack = item_location.spawn("coin_pouch", Location("player", "bob"), 1)[0]
        assert stack.id is not None
        service = LedgerService()
        service.credit(session, "player", "alice", 5)  # not enough for the coin leg

        with pytest.raises(ConflictError):
            service.execute_exchange(
                session,
                [
                    ExchangeLeg(
                        give_from=Location("player", "alice"),
                        give_to=Location("player", "bob"),
                        coins=20,
                    ),
                    ExchangeLeg(
                        give_from=Location("player", "bob"),
                        give_to=Location("player", "alice"),
                        stacks=((stack.id, 1),),
                    ),
                ],
            )

        # Neither leg applied: bob's item stayed put, alice's coins untouched.
        assert service.balance_of(session, "player", "alice") == 5
        assert StackRepo(session).stacks_for_owner("player", "bob")[0].quantity == 1
        assert StackRepo(session).stacks_for_owner("player", "alice") == []
