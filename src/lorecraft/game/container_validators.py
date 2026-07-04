"""Container move validator: open state, capacity, and nesting depth.

Registers with Sprint 16's HolderRegistry (docs/inventory_equipment.md §6).
A container's owner_id is an ItemInstance.id; this validator enforces that
the container is open, that adding the incoming item(s) wouldn't exceed its
declared capacity, and that nesting doesn't exceed a max depth.
"""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.errors import ConflictError, ValidationError
from lorecraft.game.holders import Location, get_registry as get_holder_registry
from lorecraft.models.items import ItemInstance, ItemStack
from lorecraft.models.world import Item
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.stack_repo import StackRepo

MAX_NESTING_DEPTH = 3


def _container_depth(session: Session, container_instance_id: str) -> int:
    """How many containers deep `container_instance_id` itself sits (0 = directly
    in a room/player; 1 = inside one container; etc.)."""
    depth = 0
    current_id = container_instance_id
    seen: set[str] = set()
    while True:
        if current_id in seen:
            return depth  # cycle guard; ItemLocationService already prevents cycles
        seen.add(current_id)
        statement = select(ItemStack).where(ItemStack.instance_id == current_id)
        stack = session.exec(statement).first()
        if stack is None or stack.owner_type != "container":
            return depth
        depth += 1
        current_id = stack.owner_id


def _validate_container_move(
    session: Session, dest: Location, item: object, quantity: int
) -> None:
    assert isinstance(item, Item)
    instance = session.get(ItemInstance, dest.owner_id)
    if instance is None:
        raise ValidationError(
            "Destination container does not exist", "not_found_holder"
        )

    openable_state = instance.state.get("openable")
    if isinstance(openable_state, dict) and not openable_state.get("open"):
        raise ConflictError("The container is closed", "conflict_container_closed")

    container_item_repo = ItemRepo(session)
    container_item = container_item_repo.get(instance.item_id)
    if container_item is not None and container_item.capacity is not None:
        stack_repo = StackRepo(session)
        current_weight = 0.0
        for stack in stack_repo.stacks_at(dest):
            contained_item = container_item_repo.get(stack.item_id)
            if contained_item is not None:
                current_weight += contained_item.weight * stack.quantity
        if current_weight + item.weight * quantity > container_item.capacity:
            raise ConflictError(
                "The container doesn't have room for that", "conflict_container_full"
            )

    if _container_depth(session, dest.owner_id) + 1 > MAX_NESTING_DEPTH:
        raise ConflictError(
            "That's nested too deep to put anything else in",
            "conflict_nesting_too_deep",
        )


_registered = False


def register() -> None:
    """Register the container move validator (open/capacity/nesting) on the
    holder registry. Called by the `containers` feature manifest when enabled
    (no longer a module-level import side effect). Idempotent (move validators
    are appended per holder type, so a guard prevents double-registration)."""
    global _registered
    if _registered:
        return
    _registered = True
    get_holder_registry().register_move_validator("container", _validate_container_move)
