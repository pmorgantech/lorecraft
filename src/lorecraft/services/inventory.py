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

        inv_matches = ctx.item_repo.search_player_items(
            ctx.player.inventory, name_or_id
        )
        room_matches = [
            item for _, item in ctx.item_repo.search_in_room(ctx.room.id, name_or_id)
        ]

        seen: set[str] = set()
        all_matches: list[Item] = []
        for item in inv_matches + room_matches:
            if item.id not in seen:
                seen.add(item.id)
                all_matches.append(item)

        if not all_matches:
            ctx.say("You don't see that here.")
            return

        if len(all_matches) > 1:
            _prompt_disambiguation(ctx, "examine", name_or_id, all_matches)
            return

        ctx.say(all_matches[0].description)

    def take_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Take what?")
            return

        matches = ctx.item_repo.search_in_room(ctx.room.id, name_or_id)
        if not matches:
            ctx.say("You don't see that here.")
            return

        if len(matches) > 1:
            _prompt_disambiguation(
                ctx, "take", name_or_id, [item for _, item in matches]
            )
            return

        room_item, item = matches[0]
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

        matches = ctx.item_repo.search_player_items(ctx.player.inventory, name_or_id)
        if not matches:
            ctx.say("You don't have that.")
            return

        if len(matches) > 1:
            _prompt_disambiguation(ctx, "drop", name_or_id, matches)
            return

        item = matches[0]
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


def _prompt_disambiguation(
    ctx: GameContext, verb: str, noun: str, items: list[Item]
) -> None:
    options = ", ".join(f"({i + 1}) {item.name}" for i, item in enumerate(items))
    ctx.say(f"Which do you mean? {options}")
    ctx.push_update(
        "disambig_pending",
        {"verb": verb, "noun": noun, "choices": [item.name for item in items]},
    )
