"""Ledger service — coin balances on any holder + atomic multi-leg exchange.

See docs/engine_core.md §3.7. Stateless per-call (like ItemLocationService):
every method takes the caller's Session explicitly. No engine/rng held —
there is no scheduler-driven sweep for this primitive.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlmodel import Session

from lorecraft.errors import ConflictError, NotFoundError, ValidationError
from lorecraft.engine.game.holders import (
    HolderRegistry,
    Location,
    get_registry as get_holder_registry,
)
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.ledger_repo import LedgerRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.item_location import ItemLocationService


@dataclass(frozen=True)
class ExchangeLeg:
    """One party's give/receive pair within a multi-leg exchange.

    Args:
        give_from: Where the coins/stacks currently are (slot ignored for coins).
        give_to: Where they end up.
        coins: How many coins to move (>= 0).
        stacks: (stack_id, quantity) pairs to move — each stack must actually
            be located at give_from with at least that quantity.
    """

    give_from: Location
    give_to: Location
    coins: int = 0
    stacks: tuple[tuple[int, int], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExchangeReceipt:
    """Summary of an applied execute_exchange() call."""

    leg_count: int
    total_coins_moved: int
    total_stacks_moved: int


class LedgerService:
    def balance_of(self, session: Session, holder_type: str, holder_id: str) -> int:
        balance = LedgerRepo(session).find(holder_type, holder_id)
        return balance.balance if balance is not None else 0

    def credit(
        self, session: Session, holder_type: str, holder_id: str, amount: int
    ) -> None:
        """Money creation — world import, admin, loot. The ONLY way coins
        enter play. Never commits."""
        if amount < 0:
            raise ValidationError("amount must be >= 0", "validation_negative_amount")
        self._adjust_balance(session, holder_type, holder_id, amount)

    def execute_exchange(
        self, session: Session, legs: Sequence[ExchangeLeg]
    ) -> ExchangeReceipt:
        """Atomic multi-leg exchange of coins and items.

        Validates every leg first (sufficient balances, every stack present
        at its give_from with quantity, destination holders exist); only if
        every leg passes does it apply any mutation. Never commits — the
        caller's transaction (command lifecycle) makes the whole exchange
        atomic and rollback-safe.

        Raises:
            ValidationError: A leg's coins/quantity is negative or zero-invalid.
            NotFoundError: A leg's destination holder or a referenced stack
                doesn't exist.
            ConflictError: Insufficient coin balance, a stack isn't actually
                at its declared give_from, or insufficient stack quantity.
                The error names the failing leg's index.
        """
        holder_registry = get_holder_registry()
        stack_repo = StackRepo(session)

        for index, leg in enumerate(legs):
            self._validate_leg(session, leg, index, holder_registry, stack_repo)

        item_location = ItemLocationService(
            session, stack_repo=stack_repo, item_repo=ItemRepo(session)
        )
        total_coins = 0
        total_stacks = 0
        for leg in legs:
            if leg.coins > 0:
                self._adjust_balance(
                    session,
                    leg.give_from.owner_type,
                    leg.give_from.owner_id,
                    -leg.coins,
                )
                self._adjust_balance(
                    session, leg.give_to.owner_type, leg.give_to.owner_id, leg.coins
                )
                total_coins += leg.coins
            for stack_id, quantity in leg.stacks:
                item_location.move(stack_id, leg.give_to, quantity)
                total_stacks += 1

        return ExchangeReceipt(
            leg_count=len(legs),
            total_coins_moved=total_coins,
            total_stacks_moved=total_stacks,
        )

    def _validate_leg(
        self,
        session: Session,
        leg: ExchangeLeg,
        index: int,
        holder_registry: HolderRegistry,
        stack_repo: StackRepo,
    ) -> None:
        if leg.coins < 0:
            raise ValidationError(
                f"Leg {index}: coins must be >= 0", "validation_negative_coins"
            )

        if not holder_registry.holder_exists(
            leg.give_to.owner_type, session, leg.give_to.owner_id
        ):
            raise NotFoundError(
                f"Leg {index}: destination holder does not exist", "not_found_holder"
            )

        if leg.coins > 0:
            available = self.balance_of(
                session, leg.give_from.owner_type, leg.give_from.owner_id
            )
            if available < leg.coins:
                raise ConflictError(
                    f"Leg {index}: insufficient coin balance "
                    f"(has {available}, needs {leg.coins})",
                    "conflict_insufficient_coins",
                )

        for stack_id, quantity in leg.stacks:
            if quantity < 1:
                raise ValidationError(
                    f"Leg {index}: stack quantity must be >= 1",
                    "validation_quantity_underflow",
                )
            stack = stack_repo.find_stack(stack_id)
            if stack is None:
                raise NotFoundError(
                    f"Leg {index}: stack {stack_id} does not exist", "not_found_stack"
                )
            if (
                stack.owner_type != leg.give_from.owner_type
                or stack.owner_id != leg.give_from.owner_id
            ):
                raise ConflictError(
                    f"Leg {index}: stack {stack_id} is not at the expected location",
                    "conflict_stack_location_mismatch",
                )
            if stack.quantity < quantity:
                raise ConflictError(
                    f"Leg {index}: insufficient quantity for stack {stack_id} "
                    f"(has {stack.quantity}, needs {quantity})",
                    "conflict_quantity_underflow",
                )

    def _adjust_balance(
        self, session: Session, holder_type: str, holder_id: str, delta: int
    ) -> None:
        repo = LedgerRepo(session)
        balance = repo.find(holder_type, holder_id)
        if balance is None:
            if delta < 0:
                raise ConflictError(
                    f"Insufficient balance for {holder_type}:{holder_id}",
                    "conflict_insufficient_coins",
                )
            repo.create(holder_type, holder_id, delta)
            return
        new_balance = balance.balance + delta
        if new_balance < 0:
            raise ConflictError(
                f"Insufficient balance for {holder_type}:{holder_id}",
                "conflict_insufficient_coins",
            )
        balance.balance = new_balance
        repo.save(balance)
