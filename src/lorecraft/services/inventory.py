"""Inventory and room-item service behavior."""

from __future__ import annotations

from lorecraft.game.context import GameContext
from lorecraft.game.events import GameEvent
from lorecraft.models.world import Item


class InventoryService:
    def look(self, ctx: GameContext) -> None:
        ctx.say(ctx.room.name)
        ctx.say(ctx.room.description)

        visible_exits = [
            exit_.direction
            for exit_ in ctx.room_repo.exits(ctx.room.id)
            if not exit_.hidden
        ]
        if visible_exits:
            ctx.say(f"Exits: {', '.join(sorted(visible_exits))}.")
        else:
            ctx.say("There are no obvious exits.")

        room_items = [item.name for _, item in ctx.item_repo.items_in_room(ctx.room.id)]
        if room_items:
            ctx.say(f"You see: {', '.join(sorted(room_items))}.")

        ctx.push_update("room_id", ctx.room.id)

    def inventory(self, ctx: GameContext) -> None:
        items = self._inventory_items(ctx)
        if not items:
            ctx.say("You are carrying nothing.")
            ctx.push_update("inventory", [])
            return

        ctx.say(f"You are carrying: {', '.join(item.name for item in items)}.")
        ctx.push_update("inventory", [item.id for item in items])

    def examine(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            self.look(ctx)
            return

        inventory_item = ctx.item_repo.find_player_item(
            ctx.player.inventory, name_or_id
        )
        if inventory_item is not None:
            ctx.say(inventory_item.description)
            return

        room_match = ctx.item_repo.find_in_room(ctx.room.id, name_or_id)
        if room_match is not None:
            _, item = room_match
            ctx.say(item.description)
            return

        ctx.say("You don't see that here.")

    def take_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Take what?")
            return

        match = ctx.item_repo.find_in_room(ctx.room.id, name_or_id)
        if match is None:
            ctx.say("You don't see that here.")
            return

        room_item, item = match
        if not item.takeable:
            ctx.say("You can't take that.")
            return

        ctx.item_repo.remove_from_room(room_item)
        ctx.player.inventory = [*ctx.player.inventory, item.id]

        ctx.say(f"You take {item.name}.")
        ctx.tell_room(f"{ctx.player.username} takes {item.name}.")
        ctx.push_update("inventory", list(ctx.player.inventory))
        ctx.queue_event(
            GameEvent.ITEM_TAKEN,
            player_id=ctx.player.id,
            room_id=ctx.room.id,
            item_id=item.id,
        )

    def drop_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Drop what?")
            return

        item = ctx.item_repo.find_player_item(ctx.player.inventory, name_or_id)
        if item is None:
            ctx.say("You don't have that.")
            return

        inventory = list(ctx.player.inventory)
        inventory.remove(item.id)
        ctx.player.inventory = inventory
        ctx.item_repo.increment_room_item(ctx.room.id, item.id)

        ctx.say(f"You drop {item.name}.")
        ctx.tell_room(f"{ctx.player.username} drops {item.name}.")
        ctx.push_update("inventory", list(ctx.player.inventory))
        ctx.queue_event(
            GameEvent.ITEM_DROPPED,
            player_id=ctx.player.id,
            room_id=ctx.room.id,
            item_id=item.id,
        )

    def _inventory_items(self, ctx: GameContext) -> list[Item]:
        items: list[Item] = []
        for item_id in ctx.player.inventory:
            item = ctx.item_repo.get(item_id)
            if item is not None:
                items.append(item)
        return items
