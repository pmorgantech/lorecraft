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
from lorecraft.engine.game.components import get_registry as get_component_registry
from lorecraft.engine.game.holders import (
    HolderRegistry,
    Location,
    get_registry as get_holder_registry,
)
from lorecraft.engine.models.items import ItemInstance, ItemStack
from lorecraft.engine.models.world import Item
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.stack_repo import StackRepo


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
            raise ValidationError(
                "quantity must be >= 1", "validation_quantity_underflow"
            )

        item = self.item_repo.get(item_id)
        if item is None:
            raise NotFoundError(f"Item {item_id} does not exist", "not_found_item")

        if not self.holder_registry.holder_exists(
            loc.owner_type, self.session, loc.owner_id
        ):
            raise NotFoundError(
                f"Holder {loc.owner_type}:{loc.owner_id} does not exist",
                "not_found_holder",
            )

        stacks: list[ItemStack] = []
        component_registry = get_component_registry()

        if component_registry.requires_instance(item):
            # Create instanced stacks (one instance per stack, quantity=1)
            for _ in range(quantity):
                instance = self._new_instance(item)
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
            # Create a single fungible stack, merging into an existing one if present
            existing = self.stack_repo.find_fungible_stack(loc, item_id)
            if existing is not None:
                self.stack_repo.update_stack(
                    existing, quantity=existing.quantity + quantity
                )
                stacks.append(existing)
            else:
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
            raise ValidationError(
                "quantity must be >= 1", "validation_quantity_underflow"
            )

        stack = self.stack_repo.find_stack(stack_id)
        if stack is None:
            raise NotFoundError(f"Stack {stack_id} does not exist", "not_found_stack")

        if quantity > stack.quantity:
            raise ConflictError(
                f"Cannot remove {quantity} from stack with quantity {stack.quantity}",
                "conflict_quantity_underflow",
            )

        if quantity == stack.quantity:
            self.stack_repo.delete_stack(stack)
        else:
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
            raise NotFoundError(f"Stack {stack_id} does not exist", "not_found_stack")

        if stack.instance_id is not None:
            raise ConflictError(
                "Cannot materialize an already-instanced stack",
                "conflict_already_instanced",
            )

        if stack.quantity < 2:
            raise ConflictError(
                "Cannot materialize from a stack with quantity < 2",
                "conflict_insufficient_quantity",
            )

        item = self.item_repo.get(stack.item_id)
        if item is None:
            raise NotFoundError(
                f"Item {stack.item_id} does not exist", "not_found_item"
            )

        instance = self._new_instance(item)
        new_stack = self.stack_repo.create_stack(
            item_id=stack.item_id,
            owner_type=stack.owner_type,
            owner_id=stack.owner_id,
            quantity=1,
            slot=stack.slot,
            instance_id=instance.id,
        )
        self.stack_repo.update_stack(stack, quantity=stack.quantity - 1)

        return new_stack

    def move(self, stack_id: int, dest: Location, quantity: int) -> ItemStack:
        """THE move primitive — atomically move quantity from a stack to a destination.

        Validates: source exists with sufficient quantity, destination holder exists,
        all move validators pass (capacity, slot occupancy, etc.), no container cycles.
        Splits when quantity < stack.quantity; merges into an existing fungible dest stack.
        All-or-nothing within the caller's session (no partial application).

        Never commits; caller's transaction makes it atomic and rollback-safe.

        Args:
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
            raise ValidationError(
                "quantity must be >= 1", "validation_quantity_underflow"
            )

        stack = self.stack_repo.find_stack(stack_id)
        if stack is None:
            raise NotFoundError(f"Stack {stack_id} does not exist", "not_found_stack")

        if quantity > stack.quantity:
            raise ConflictError(
                f"Cannot move {quantity} from stack with quantity {stack.quantity}",
                "conflict_quantity_underflow",
            )

        item = self.item_repo.get(stack.item_id)
        if item is None:
            raise NotFoundError(
                f"Item {stack.item_id} does not exist", "not_found_item"
            )

        if not self.holder_registry.holder_exists(
            dest.owner_type, self.session, dest.owner_id
        ):
            raise NotFoundError(
                f"Holder {dest.owner_type}:{dest.owner_id} does not exist",
                "not_found_holder",
            )

        if dest.owner_type == "container":
            self._check_container_cycle(stack.instance_id, dest.owner_id)

        for validator in self.holder_registry.get_validators(dest.owner_type):
            validator(self.session, dest, item, quantity)

        dest_stack: ItemStack

        if stack.instance_id is not None:
            if quantity != stack.quantity or quantity != 1:
                raise ConflictError(
                    "Cannot partially move an instanced item (quantity must be 1)",
                    "conflict_instanced_partial_move",
                )
            stack.owner_type = dest.owner_type
            stack.owner_id = dest.owner_id
            stack.slot = dest.slot
            self.session.add(stack)
            dest_stack = stack
        else:
            existing_dest = self.stack_repo.find_fungible_stack(dest, stack.item_id)

            if existing_dest is not None and existing_dest.id != stack.id:
                existing_dest.quantity += quantity
                self.session.add(existing_dest)
                dest_stack = existing_dest
                if quantity == stack.quantity:
                    self.stack_repo.delete_stack(stack)
                else:
                    self.stack_repo.update_stack(
                        stack, quantity=stack.quantity - quantity
                    )
            elif quantity == stack.quantity:
                # Move the entire stack (no merge target, or merging with itself)
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
                self.stack_repo.update_stack(stack, quantity=stack.quantity - quantity)

        return dest_stack

    def _new_instance(self, item: Item) -> ItemInstance:
        """Create and flush a fresh ItemInstance with initialized component state."""
        instance = ItemInstance(id=str(uuid.uuid4()), item_id=item.id, state={})
        component_registry = get_component_registry()
        for component_def in component_registry.components_for(item):
            instance.state[component_def.name] = component_def.initial_state(item)
        self.session.add(instance)
        self.session.flush()
        return instance

    def _check_container_cycle(
        self, moved_instance_id: str | None, container_id: str
    ) -> None:
        """Check if moving an item into container_id would create a cycle.

        A container may not contain itself, directly or transitively: this
        walks container_id's own ancestry (the chain of containers it is
        itself sitting inside) looking for moved_instance_id. A non-instanced
        item (moved_instance_id is None) can never itself be a container, so
        it can never be its own ancestor — no cycle possible.

        Args:
            moved_instance_id: The ItemInstance.id of the item being moved,
                if it's instanced (only instanced items can be containers).
            container_id: The container (ItemInstance.id) being moved into.

        Raises:
            ConflictError: If a cycle is detected.
        """
        if moved_instance_id is None:
            return

        current_id: str | None = container_id
        seen: set[str] = set()
        while current_id is not None:
            if current_id == moved_instance_id:
                raise ConflictError(
                    "Cannot place a container inside itself",
                    "conflict_container_cycle",
                )
            if current_id in seen:
                return  # already-cyclic elsewhere; not this move's problem
            seen.add(current_id)

            statement = select(ItemStack).where(ItemStack.instance_id == current_id)
            container_stack = self.session.exec(statement).first()
            if container_stack is None or container_stack.owner_type != "container":
                return
            current_id = container_stack.owner_id
