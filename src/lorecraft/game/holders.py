"""Item holder registry and location model.

Holders are entities that can own items: players, rooms, containers, shops, banks, etc.
The holder registry defines which holder types exist and validates moves into them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class Location:
    """Location of an item: where it lives and its position within that holder."""

    owner_type: str  # "player", "room", "container", etc. (must be registered)
    owner_id: str  # UUID or ID specific to the holder
    slot: str | None = None  # Sub-position (e.g., equipment slot); None = loose/default


@dataclass(frozen=True)
class HolderTypeDef:
    """Definition of a holder type.

    Args:
        name: Unique holder type identifier (e.g., "player", "room").
        exists: Predicate to check if a holder with a given ID exists.
    """

    name: str
    exists: Callable[[Session, str], bool]


class HolderRegistry:
    """Registry for item holder types and move validators.

    Tier 1 registers built-in holders (player, room, container).
    Tier 2 registers specialized holders (shop, escrow, bank_account, etc.).
    """

    def __init__(self) -> None:
        self._holders: dict[str, HolderTypeDef] = {}
        self._move_validators: dict[str, list[Callable]] = {}

    def register(self, holder: HolderTypeDef) -> None:
        """Register a holder type.

        Args:
            holder: The HolderTypeDef to register.

        Raises:
            ValueError: If a holder with the same name is already registered.
        """
        if holder.name in self._holders:
            raise ValueError(f"Holder type '{holder.name}' already registered")
        self._holders[holder.name] = holder
        self._move_validators[holder.name] = []

    def register_move_validator(
        self,
        owner_type: str,
        validator: Callable[[Session, Location, object, int], None],
    ) -> None:
        """Register a move validator for a holder type.

        Validators are called during ItemLocationService.move() to enforce
        mechanical constraints (capacity, slot occupancy, wearability, etc.).
        They should raise typed errors to veto the move.

        Args:
            owner_type: The holder type to register a validator for.
            validator: Function(session, destination_location, item, quantity) that raises
                      on constraint violation.

        Raises:
            ValueError: If the owner_type is not registered.
        """
        if owner_type not in self._holders:
            raise ValueError(f"Unknown holder type '{owner_type}'")
        self._move_validators[owner_type].append(validator)

    def holder_exists(self, holder_type: str, session: Session, holder_id: str) -> bool:
        """Check if a holder of the given type exists.

        Args:
            holder_type: The type of holder to check.
            session: Database session for existence queries.
            holder_id: The ID of the holder to check.

        Returns:
            True if the holder exists, False otherwise.

        Raises:
            ValueError: If holder_type is not registered.
        """
        if holder_type not in self._holders:
            raise ValueError(f"Unknown holder type '{holder_type}'")
        return self._holders[holder_type].exists(session, holder_id)

    def get_validators(self, owner_type: str) -> list[Callable]:
        """Get move validators for a holder type.

        Args:
            owner_type: The holder type.

        Returns:
            List of validator functions registered for this holder type.

        Raises:
            ValueError: If holder_type is not registered.
        """
        if owner_type not in self._holders:
            raise ValueError(f"Unknown holder type '{owner_type}'")
        return self._move_validators[owner_type]

    def __contains__(self, holder_type: str) -> bool:
        """Check if a holder type is registered."""
        return holder_type in self._holders


_global_registry: HolderRegistry | None = None


def get_registry() -> HolderRegistry:
    """Get the global holder registry (lazy-initialized)."""
    global _global_registry
    if _global_registry is None:
        _global_registry = HolderRegistry()
    return _global_registry
