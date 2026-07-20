"""Ledger service — coin balances on any holder + atomic multi-leg exchange.

See docs/engine/engine_core.md §3.7. Stateless per-call (like ItemLocationService):
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
from lorecraft.engine.models.items import ItemStack
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

        Validates the whole exchange first — every leg's structural shape
        (non-negative coins, destination holders exist, stacks are actually
        at their declared give_from), *and* the net coin/quantity effect of
        all legs combined against each holder/stack's current state — before
        applying any mutation. Never commits — the caller's transaction
        (command lifecycle) makes the whole exchange atomic and
        rollback-safe.

        Validating net effect (not leg-by-leg against a stale snapshot)
        matters because legs can share a holder or a stack: two legs each
        debiting the same holder 80 coins from a 100-coin balance would each
        look individually valid against that same starting balance, even
        though applying both together overdraws it. Accumulating first and
        validating the combined delta once catches that up front, so a
        failure never surfaces after some legs have already mutated session
        state.

        Raises:
            ValidationError: A leg's coins/quantity is negative or zero-invalid.
            NotFoundError: A leg's destination holder or a referenced stack
                doesn't exist.
            ConflictError: A stack isn't actually at its declared give_from,
                or the net coin/quantity effect across all legs would
                overdraw a holder's balance or a stack's quantity. Balance/
                quantity errors name the holder/stack, not a single leg
                index — the shortfall may be the combined effect of several.
        """
        holder_registry = get_holder_registry()
        stack_repo = StackRepo(session)

        self._validate_legs(session, legs, holder_registry, stack_repo)

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

    def _validate_legs(
        self,
        session: Session,
        legs: Sequence[ExchangeLeg],
        holder_registry: HolderRegistry,
        stack_repo: StackRepo,
    ) -> None:
        """Structural per-leg checks, then one accumulated-delta check per
        holder/stack across the whole exchange (see execute_exchange)."""
        coin_deltas: dict[tuple[str, str], int] = {}
        stack_deltas: dict[int, int] = {}
        stacks_by_id: dict[int, ItemStack] = {}

        for index, leg in enumerate(legs):
            if leg.coins < 0:
                raise ValidationError(
                    f"Leg {index}: coins must be >= 0", "validation_negative_coins"
                )

            if not holder_registry.holder_exists(
                leg.give_to.owner_type, session, leg.give_to.owner_id
            ):
                raise NotFoundError(
                    f"Leg {index}: destination holder does not exist",
                    "not_found_holder",
                )

            if leg.coins > 0:
                give_key = (leg.give_from.owner_type, leg.give_from.owner_id)
                receive_key = (leg.give_to.owner_type, leg.give_to.owner_id)
                coin_deltas[give_key] = coin_deltas.get(give_key, 0) - leg.coins
                coin_deltas[receive_key] = coin_deltas.get(receive_key, 0) + leg.coins

            for stack_id, quantity in leg.stacks:
                if quantity < 1:
                    raise ValidationError(
                        f"Leg {index}: stack quantity must be >= 1",
                        "validation_quantity_underflow",
                    )
                stack = stacks_by_id.get(stack_id)
                if stack is None:
                    stack = stack_repo.find_stack(stack_id)
                    if stack is None:
                        raise NotFoundError(
                            f"Leg {index}: stack {stack_id} does not exist",
                            "not_found_stack",
                        )
                    stacks_by_id[stack_id] = stack
                if (
                    stack.owner_type != leg.give_from.owner_type
                    or stack.owner_id != leg.give_from.owner_id
                ):
                    raise ConflictError(
                        f"Leg {index}: stack {stack_id} is not at the expected "
                        "location",
                        "conflict_stack_location_mismatch",
                    )
                stack_deltas[stack_id] = stack_deltas.get(stack_id, 0) + quantity

        for (holder_type, holder_id), delta in coin_deltas.items():
            if delta >= 0:
                continue
            available = self.balance_of(session, holder_type, holder_id)
            if available + delta < 0:
                raise ConflictError(
                    f"{holder_type}:{holder_id}: insufficient coin balance across "
                    f"the exchange (has {available}, needs {-delta})",
                    "conflict_insufficient_coins",
                )

        for stack_id, needed in stack_deltas.items():
            stack = stacks_by_id[stack_id]
            if stack.quantity < needed:
                raise ConflictError(
                    f"stack {stack_id}: insufficient quantity across the exchange "
                    f"(has {stack.quantity}, needs {needed})",
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
