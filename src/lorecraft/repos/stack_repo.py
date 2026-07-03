"""Item stack repository — data access for ItemStack rows."""

from __future__ import annotations

from sqlmodel import Session, and_, func, select

from lorecraft.game.holders import Location
from lorecraft.models.items import ItemStack


class StackRepo:
    """Data access for ItemStack queries and mutations.

    Handles row-level operations; semantics (move validation, cycle checking, etc.)
    live in ItemLocationService.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def stacks_at(self, loc: Location) -> list[ItemStack]:
        """Get all stacks at a location, ordered by creation (ID).

        Args:
            loc: The Location to query.

        Returns:
            List of ItemStack rows at this location, ordered by ID (deterministic).
        """
        statement = (
            select(ItemStack)
            .where(
                ItemStack.owner_type == loc.owner_type,
                ItemStack.owner_id == loc.owner_id,
                ItemStack.slot == loc.slot,
            )
            .order_by(ItemStack.id)  # type: ignore[arg-type]
        )
        return list(self.session.exec(statement).all())

    def stacks_for_owner(self, owner_type: str, owner_id: str) -> list[ItemStack]:
        """Get all stacks owned by an entity, regardless of slot.

        Used for full inventory/contents listings.

        Args:
            owner_type: The holder type.
            owner_id: The holder ID.

        Returns:
            List of all ItemStack rows for this owner, ordered by ID.
        """
        statement = (
            select(ItemStack)
            .where(
                ItemStack.owner_type == owner_type,
                ItemStack.owner_id == owner_id,
            )
            .order_by(ItemStack.id)  # type: ignore[arg-type]
        )
        return list(self.session.exec(statement).all())

    def quantity_of(self, loc: Location, item_id: str) -> int:
        """Get total quantity of an item at a location.

        Sums quantities across all stacks of the given item_id.

        Args:
            loc: The Location to query.
            item_id: The item ID to sum.

        Returns:
            Total quantity at this location (0 if no stacks).
        """
        statement = select(func.coalesce(func.sum(ItemStack.quantity), 0)).where(
            ItemStack.owner_type == loc.owner_type,
            ItemStack.owner_id == loc.owner_id,
            ItemStack.slot == loc.slot,
            ItemStack.item_id == item_id,
        )
        result = self.session.exec(statement).one()
        return int(result)

    def find_stack(self, stack_id: int) -> ItemStack | None:
        """Retrieve a stack by ID.

        Args:
            stack_id: The ItemStack.id.

        Returns:
            The ItemStack row, or None if not found.
        """
        return self.session.get(ItemStack, stack_id)

    def find_fungible_stack(self, loc: Location, item_id: str) -> ItemStack | None:
        """Find the fungible (non-instanced) stack for an item at a location.

        There is at most one per (owner_type, owner_id, slot, item_id).

        Args:
            loc: The Location.
            item_id: The Item ID.

        Returns:
            The fungible ItemStack if one exists, None otherwise.
        """
        statement = select(ItemStack).where(
            and_(
                ItemStack.owner_type == loc.owner_type,
                ItemStack.owner_id == loc.owner_id,
                ItemStack.slot == loc.slot,
                ItemStack.item_id == item_id,
                ItemStack.instance_id.is_(None),  # type: ignore[attr-defined]
            )
        )
        return self.session.exec(statement).first()

    def create_stack(
        self,
        item_id: str,
        owner_type: str,
        owner_id: str,
        quantity: int = 1,
        slot: str | None = None,
        instance_id: str | None = None,
    ) -> ItemStack:
        """Create a new ItemStack row.

        Does not commit; caller owns transaction.

        Args:
            item_id: The Item ID.
            owner_type: The holder type.
            owner_id: The holder ID.
            quantity: Quantity (must be >= 1).
            slot: Optional slot name.
            instance_id: Optional instance ID (only for quantity=1 items).

        Returns:
            The newly created ItemStack row.
        """
        stack = ItemStack(
            item_id=item_id,
            owner_type=owner_type,
            owner_id=owner_id,
            quantity=quantity,
            slot=slot,
            instance_id=instance_id,
        )
        self.session.add(stack)
        self.session.flush()  # Populate ID
        return stack

    def update_stack(self, stack: ItemStack, quantity: int | None = None) -> None:
        """Update a stack's quantity.

        Does not commit; caller owns transaction.

        Args:
            stack: The ItemStack to update.
            quantity: New quantity (if None, no change to quantity).
        """
        if quantity is not None:
            stack.quantity = quantity
        self.session.add(stack)

    def delete_stack(self, stack: ItemStack) -> None:
        """Delete a stack.

        Does not commit; caller owns transaction.

        Args:
            stack: The ItemStack row to delete.
        """
        self.session.delete(stack)

    def delete_stack_by_id(self, stack_id: int) -> None:
        """Delete a stack by ID.

        Does not commit; caller owns transaction.

        Args:
            stack_id: The ItemStack.id to delete.
        """
        stack = self.find_stack(stack_id)
        if stack is not None:
            self.session.delete(stack)
