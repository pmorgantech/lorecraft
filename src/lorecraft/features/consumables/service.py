"""Consumable-item service: the eat/drink/quaff behavior.

A distinct concern from take/drop/use/wear (which live in `InventoryService`):
consuming destroys one unit of a *held* food/drink item and fires its one-shot
`heal`/`apply_effect` descriptors (see `effects.py`). Item resolution is reused
from `InventoryService.find_carried_item` rather than reimplemented, so eat/drink
disambiguate and error exactly like the other item verbs.
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

        resolved = self._inventory.find_carried_item(name_or_id, ctx, verb=verb)
        if resolved is None:
            return
        stack, item = resolved

        if item.category != category:
            ctx.say(f"You can't {verb} that.", MessageType.WARNING)
            return

        # Narrate the act, then fire the item's one-shot effects (each emits its
        # own message), then destroy exactly one unit of the consumed stack.
        ctx.say(f"You {verb} the {item.name}.")
        ctx.tell_room(f"{ctx.player.username} {verb}s the {item.name}.")
        apply_consumable_effects(item, ctx)

        assert stack.id is not None
        ctx.item_location.destroy(stack.id, 1)
        ctx.push_update(
            "inventory",
            inventory_update_entries(ctx.item_repo.stacks_carried_by(ctx.player.id)),
        )
