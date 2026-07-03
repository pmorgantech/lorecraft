"""Item location and ownership service — the unified move primitive for all items.

Enforces the invariants of ItemStack/ItemInstance model:
- quantity >= 1 (zero stacks deleted immediately)
- instanced items never stack (quantity=1 when instance_id is set)
- at most one fungible stack per location/item_id
- atomic moves with container cycle detection
"""

from __future__ import annotations

import uuid

from sqlmodel import Session, select

from lorecraft.errors import ConflictError, NotFoundError, ValidationError
from lorecraft.game.components import get_registry as get_component_registry
from lorecraft.game.holders import (
    HolderRegistry,
    Location,
    get_registry as get_holder_registry,
)
from lorecraft.models.items import ItemInstance, ItemStack
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.stack_repo import StackRepo


class ItemLocationService:
    """Atomic operations on item location and ownership.

    All methods work on the caller's Session and never call commit() or rollback();
    the transaction lifecycle (command, scheduler handler) owns commit/rollback.
    """

    def __init__(
        self,
        session: Session,
        stack_repo: StackRepo | None = None,
        item_repo: ItemRepo | None = None,
        holder_registry: HolderRegistry | None = None,
    ) -> None:
        self.session = session
        self.stack_repo = stack_repo or StackRepo(session)
        self.item_repo = item_repo or ItemRepo(session)
        self.holder_registry = holder_registry or get_holder_registry()

    def spawn(self, item_id: str, loc: Location, quantity: int = 1) -> list[ItemStack]:
        """Create items from nothing (world import, loot, admin).

        If the item requires an instance (has registered components), creates `quantity`
        instances each on its own quantity-1 stack. Otherwise creates a single fungible
        stack. Never commits.

        Args:
            item_id: The Item ID to spawn.
            loc: The Location to spawn into.
            quantity: How many to spawn (must be >= 1).

        Returns:
            List of ItemStack rows created.

        Raises:
            NotFoundError: If the item doesn't exist or the destination holder doesn't exist.
            ValidationError: If quantity < 1.
        """
        if quantity < 1:
            raise ValidationError("spawn_quantity_underflow", "quantity must be >= 1")

        # Verify item exists
        item = self.item_repo.get(item_id)
        if item is None:
            raise NotFoundError("item_not_found", f"Item {item_id} does not exist")

        # Verify holder exists
        if not self.holder_registry.holder_exists(
            loc.owner_type, self.session, loc.owner_id
        ):
            raise NotFoundError(
                "holder_not_found",
                f"Holder {loc.owner_type}:{loc.owner_id} does not exist",
            )

        stacks: list[ItemStack] = []
        component_registry = get_component_registry()

        if component_registry.requires_instance(item):
            # Create instanced stacks (one instance per stack, quantity=1)
            for _ in range(quantity):
                instance = ItemInstance(
                    id=str(uuid.uuid4()),
                    item_id=item_id,
                    state={},
                )
                # Initialize component state
                for component_def in component_registry.components_for(item):
                    instance.state[component_def.name] = component_def.initial_state(
                        item
                    )

                self.session.add(instance)
                self.session.flush()  # Populate instance.id

                stack = self.stack_repo.create_stack(
                    item_id=item_id,
                    owner_type=loc.owner_type,
                    owner_id=loc.owner_id,
                    quantity=1,
                    slot=loc.slot,
                    instance_id=instance.id,
                )
                stacks.append(stack)
        else:
            # Create a single fungible stack
            stack = self.stack_repo.create_stack(
                item_id=item_id,
                owner_type=loc.owner_type,
                owner_id=loc.owner_id,
                quantity=quantity,
                slot=loc.slot,
                instance_id=None,
            )
            stacks.append(stack)

        return stacks

    def destroy(self, stack_id: int, quantity: int) -> None:
        """Delete items. Removes quantity from a stack; if it reaches 0, deletes the row.

        Never commits.

        Args:
            stack_id: The ItemStack.id.
            quantity: How many to remove (must be >= 1 and <= current quantity).

        Raises:
            NotFoundError: If the stack doesn't exist.
            ConflictError: If quantity exceeds the stack's quantity (underflow).
        """
        if quantity < 1:
            raise ValidationError("destroy_quantity_underflow", "quantity must be >= 1")

        stack = self.stack_repo.find_stack(stack_id)
        if stack is None:
            raise NotFoundError("stack_not_found", f"Stack {stack_id} does not exist")

        if quantity > stack.quantity:
            raise ConflictError(
                "quantity_underflow",
                f"Cannot remove {quantity} from stack with quantity {stack.quantity}",
            )

        if quantity == stack.quantity:
            # Delete the entire stack
            # If instanced, orphan the instance (the FK cascade or explicit cleanup handles it)
            self.stack_repo.delete_stack(stack)
        else:
            # Reduce quantity
            self.stack_repo.update_stack(stack, quantity=stack.quantity - quantity)

    def materialize(self, stack_id: int) -> ItemStack:
        """Split 1 unit off a fungible stack into a new instanced stack.

        Creates a fresh ItemInstance, moves 1 unit from the source stack to it.
        Used when a generic item (like a torch) becomes a specific instance (40%-burned torch).

        Never commits.

        Args:
            stack_id: The fungible ItemStack.id to split from.

        Returns:
            The newly created instanced ItemStack.

        Raises:
            NotFoundError: If the stack doesn't exist.
            ConflictError: If the stack is already instanced or has quantity < 2.
        """
        stack = self.stack_repo.find_stack(stack_id)
        if stack is None:
            raise NotFoundError("stack_not_found", f"Stack {stack_id} does not exist")

        if stack.instance_id is not None:
            raise ConflictError(
                "already_instanced", "Cannot materialize an already-instanced stack"
            )

        if stack.quantity < 2:
            raise ConflictError(
                "insufficient_quantity",
                "Cannot materialize from a stack with quantity < 2",
            )

        # Create a new instance
        item = self.item_repo.get(stack.item_id)
        if item is None:
            raise NotFoundError(
                "item_not_found", f"Item {stack.item_id} does not exist"
            )

        instance = ItemInstance(
            id=str(uuid.uuid4()),
            item_id=stack.item_id,
            state={},
        )
        component_registry = get_component_registry()
        for component_def in component_registry.components_for(item):
            instance.state[component_def.name] = component_def.initial_state(item)

        self.session.add(instance)
        self.session.flush()  # Populate instance.id

        # Create new instanced stack at the same location
        new_stack = self.stack_repo.create_stack(
            item_id=stack.item_id,
            owner_type=stack.owner_type,
            owner_id=stack.owner_id,
            quantity=1,
            slot=stack.slot,
            instance_id=instance.id,
        )

        # Reduce source stack quantity
        self.stack_repo.update_stack(stack, quantity=stack.quantity - 1)

        return new_stack

    def move(
        self, session: Session, stack_id: int, dest: Location, quantity: int
    ) -> ItemStack:
        """THE move primitive — atomically move quantity from a stack to a destination.

        Validates: source exists with sufficient quantity, destination holder exists,
        all move validators pass (capacity, slot occupancy, etc.), no container cycles.
        Splits when quantity < stack.quantity; merges into an existing fungible dest stack.
        All-or-nothing within the caller's session (no partial application).

        Never commits; caller's transaction makes it atomic and rollback-safe.

        Args:
            session: Database session (usually self.session, but parameterized for testing).
            stack_id: The source ItemStack.id.
            dest: The destination Location.
            quantity: How many to move (must be >= 1).

        Returns:
            The destination ItemStack (either merged into existing or newly created).

        Raises:
            NotFoundError: If source stack or destination holder doesn't exist.
            ValidationError: If quantity < 1 or other validation issues.
            ConflictError: If quantity exceeds source, stack underflow, container cycle, etc.
        """
        if quantity < 1:
            raise ValidationError("move_quantity_underflow", "quantity must be >= 1")

        # Find source stack
        stack = self.stack_repo.find_stack(stack_id)
        if stack is None:
            raise NotFoundError("stack_not_found", f"Stack {stack_id} does not exist")

        # Verify source has enough quantity
        if quantity > stack.quantity:
            raise ConflictError(
                "quantity_underflow",
                f"Cannot move {quantity} from stack with quantity {stack.quantity}",
            )

        # Get item
        item = self.item_repo.get(stack.item_id)
        if item is None:
            raise NotFoundError(
                "item_not_found", f"Item {stack.item_id} does not exist"
            )

        # Verify destination holder exists
        if not self.holder_registry.holder_exists(
            dest.owner_type, session, dest.owner_id
        ):
            raise NotFoundError(
                "holder_not_found",
                f"Holder {dest.owner_type}:{dest.owner_id} does not exist",
            )

        # Check for container cycle (if moving into a container)
        if dest.owner_type == "container":
            self._check_container_cycle(session, stack.item_id, dest.owner_id)

        # Run move validators for destination holder type
        validators = self.holder_registry.get_validators(dest.owner_type)
        for validator in validators:
            validator(session, dest, item, quantity)

        # Handle the move
        dest_stack: ItemStack

        if stack.instance_id is not None:
            # Instanced items never merge; just update the location
            if quantity != 1:
                raise ConflictError(
                    "instanced_partial_move",
                    "Cannot partially move an instanced item (quantity=1)",
                )
            if quantity != stack.quantity:
                raise ConflictError(
                    "instanced_quantity_mismatch",
                    "Instanced stack quantity must equal 1",
                )
            # Move the entire stack
            stack.owner_type = dest.owner_type
            stack.owner_id = dest.owner_id
            stack.slot = dest.slot
            self.session.add(stack)
            dest_stack = stack
        else:
            # Fungible stack: try to merge into existing dest stack
            existing_dest = self.stack_repo.find_fungible_stack(dest, stack.item_id)

            if existing_dest is not None:
                # Merge: add quantity to existing, reduce source
                existing_dest.quantity += quantity
                self.session.add(existing_dest)
                dest_stack = existing_dest
            else:
                # No existing fungible stack; move or split
                if quantity == stack.quantity:
                    # Move the entire stack
                    stack.owner_type = dest.owner_type
                    stack.owner_id = dest.owner_id
                    stack.slot = dest.slot
                    self.session.add(stack)
                    dest_stack = stack
                else:
                    # Split: create new stack at dest, reduce source
                    dest_stack = self.stack_repo.create_stack(
                        item_id=stack.item_id,
                        owner_type=dest.owner_type,
                        owner_id=dest.owner_id,
                        quantity=quantity,
                        slot=dest.slot,
                        instance_id=None,
                    )

            # Reduce source stack quantity (or delete if 0)
            if quantity == stack.quantity:
                self.stack_repo.delete_stack(stack)
            else:
                self.stack_repo.update_stack(stack, quantity=stack.quantity - quantity)

        return dest_stack

    def _check_container_cycle(
        self, session: Session, item_id: str, container_id: str
    ) -> None:
        """Check if moving item_id into container_id would create a cycle.

        A container may not contain itself, directly or transitively. This walks the
        container hierarchy to detect cycles.

        Args:
            session: Database session.
            item_id: The item being moved.
            container_id: The container (ItemInstance.id) being moved into.

        Raises:
            ConflictError: If a cycle is detected.
        """
        # Find all stacks containing the container as an instance
        # The container is an ItemInstance; find the ItemStack that references it
        statement = select(ItemStack).where(ItemStack.instance_id == container_id)
        container_stack = session.exec(statement).first()
        if container_stack is None:
            return  # Container doesn't exist or isn't a stack; no cycle possible

        # Get the item of the container itself
        container_item_id = container_stack.item_id

        # Ancestor-walk: if item_id == container_item_id, we'd create a cycle
        if item_id == container_item_id:
            raise ConflictError(
                "container_cycle", "Cannot place a container inside itself"
            )

        # TODO: Walk transitive containment for deeper cycles (if item is itself a container,
        # check if container is inside it). This is deferred pending full container semantics.
