"""Consumable-item service: the eat/drink/quaff behavior.

A distinct concern from take/drop/use/wear (which live in `InventoryService`):
consuming destroys one unit of a *held* food/drink item and fires its one-shot
`heal`/`apply_effect` descriptors (see `effects.py`). Drink can also target a
non-takeable room fixture, such as a fountain, and applies the same descriptors
without destroying the fixture. Item resolution is reused from `InventoryService`
rather than reimplemented, so eat/drink disambiguate and error exactly like the
other item verbs.
"""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.features.consumables.effects import apply_consumable_effects
from lorecraft.features.inventory.service import (
    InventoryService,
    inventory_update_entries,
)

FOOD_CATEGORY = "food"
DRINK_CATEGORY = "drink"


class ConsumableService:
    """Handles `eat`/`drink`/`quaff`. Composes `InventoryService` for the shared
    held-item resolution; otherwise stateless like the other gameplay services."""

    def __init__(self, inventory: InventoryService | None = None) -> None:
        self._inventory = inventory or InventoryService()

    def eat(self, name_or_id: str | None, ctx: GameContext) -> None:
        self._consume(name_or_id, ctx, verb="eat", category=FOOD_CATEGORY)

    def drink(self, name_or_id: str | None, ctx: GameContext) -> None:
        self._consume(name_or_id, ctx, verb="drink", category=DRINK_CATEGORY)

    def _consume(
        self, name_or_id: str | None, ctx: GameContext, *, verb: str, category: str
    ) -> None:
        if name_or_id is None:
            ctx.say(f"{verb.capitalize()} what?", MessageType.WARNING)
            return

        carried_matches = ctx.item_repo.search_player_items(ctx.player.id, name_or_id)
        resolved = self._inventory.find_carried_item(
            name_or_id,
            ctx,
            verb=verb,
            not_found_msg=None
            if category == DRINK_CATEGORY
            else "You don't have that.",
        )
        if resolved is None and carried_matches:
            return
        if resolved is None and category == DRINK_CATEGORY:
            resolved = self._inventory.find_room_item(
                name_or_id, ctx, verb=verb, not_found_msg="You don't have that."
            )
        if resolved is None:
            return
        stack, item = resolved

        if item.category != category:
            ctx.say(f"You can't {verb} that.", MessageType.WARNING)
            return

        if stack.owner_type == "room" and item.takeable:
            ctx.say(f"Take the {item.name} first.", MessageType.WARNING)
            return

        # Narrate the act, then fire the item's one-shot effects (each emits its
        # own message). Held items are destroyed; room fixtures are persistent
        # drink sources.
        ctx.say(f"You {verb} the {item.name}.")
        ctx.tell_room(f"{ctx.player.username} {verb}s the {item.name}.")
        apply_consumable_effects(item, ctx)

        if stack.owner_type == "room":
            return

        assert stack.id is not None
        ctx.item_location.destroy(stack.id, 1)
        ctx.push_update(
            "inventory",
            inventory_update_entries(ctx.item_repo.stacks_carried_by(ctx.player.id)),
        )
