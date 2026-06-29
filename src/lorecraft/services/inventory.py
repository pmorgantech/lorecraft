"""Inventory and room-item service behavior."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from lorecraft.game.context import GameContext
from lorecraft.game.events import GameEvent
from lorecraft.models.world import Item, RoomItem


def grouped_inventory_ids(item_ids: Sequence[str]) -> list[tuple[str, int]]:
    """Group repeated item IDs, preserving first-seen order."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for item_id in item_ids:
        if item_id not in counts:
            order.append(item_id)
            counts[item_id] = 0
        counts[item_id] += 1
    return [(item_id, counts[item_id]) for item_id in order]


def format_inventory_entry(name: str, quantity: int) -> str:
    """Format one inventory row for player-facing text."""
    if quantity > 1:
        return f"[{quantity}] {name}"
    return name


def format_inventory_summary(
    item_ids: Sequence[str],
    get_item: Callable[[str], Item | None],
) -> str:
    """Comma-separated inventory list with grouped quantities."""
    labels: list[str] = []
    for item_id, quantity in grouped_inventory_ids(item_ids):
        item = get_item(item_id)
        if item is not None:
            labels.append(format_inventory_entry(item.name, quantity))
    return ", ".join(labels)


def format_room_items_summary(
    room_items: Sequence[tuple[RoomItem, Item]],
) -> str:
    """Comma-separated room item list with grouped quantities."""
    labels = [
        format_inventory_entry(item.name, room_item.quantity)
        for room_item, item in room_items
    ]
    return ", ".join(sorted(labels))


@dataclass(frozen=True)
class ItemTarget:
    """Parsed item reference from a take/drop noun phrase."""

    query: str
    quantity: int = 1
    take_all: bool = False
    index: int | None = None


_INDEX_TARGET_RE = re.compile(r"^(\d+)\.\s*(.+)$", re.IGNORECASE)
_QUANTITY_TARGET_RE = re.compile(r"^(\d+)\s+(.+)$")


def parse_item_target(noun: str) -> ItemTarget:
    """Parse quantity, all, or indexed selectors from a noun phrase.

    Examples:
        ``all coin`` -> take/drop every matching item
        ``2 coin`` / ``2 coins`` -> quantity 2
        ``2.coin`` -> the second matching instance
    """
    text = noun.strip()
    lowered = text.casefold()
    if lowered.startswith("all "):
        return ItemTarget(query=text[4:].strip(), take_all=True)

    index_match = _INDEX_TARGET_RE.match(text)
    if index_match:
        return ItemTarget(
            query=index_match.group(2).strip(),
            index=int(index_match.group(1)),
        )

    quantity_match = _QUANTITY_TARGET_RE.match(text)
    if quantity_match:
        return ItemTarget(
            query=quantity_match.group(2).strip(),
            quantity=int(quantity_match.group(1)),
        )

    return ItemTarget(query=text)


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

        room_items = list(ctx.item_repo.items_in_room(ctx.room.id))
        if room_items:
            summary = format_room_items_summary(room_items)
            ctx.say(f"You see: {summary}.")

        ctx.push_update("room_id", ctx.room.id)

    def inventory(self, ctx: GameContext) -> None:
        if not ctx.player.inventory:
            ctx.say("You are carrying nothing.")
            ctx.push_update("inventory", [])
            return

        summary = format_inventory_summary(ctx.player.inventory, ctx.item_repo.get)
        ctx.say(f"You are carrying: {summary}.")
        ctx.push_update("inventory", list(ctx.player.inventory))

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

        target = parse_item_target(name_or_id)
        if target.index is not None:
            self._take_indexed(target, ctx)
            return
        if target.take_all:
            self._take_quantity(target, ctx, take_all=True)
            return
        if target.quantity > 1:
            self._take_quantity(target, ctx, take_all=False)
            return
        self._take_one(target.query, ctx)

    def drop_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Drop what?")
            return

        target = parse_item_target(name_or_id)
        if target.index is not None:
            self._drop_indexed(target, ctx)
            return
        if target.take_all:
            self._drop_quantity(target, ctx, drop_all=True)
            return
        if target.quantity > 1:
            self._drop_quantity(target, ctx, drop_all=False)
            return
        self._drop_one(target.query, ctx)

    def _take_one(self, query: str, ctx: GameContext) -> None:
        matches = ctx.item_repo.search_in_room(ctx.room.id, query)
        if not matches:
            ctx.say("You don't see that here.")
            return

        if len(matches) > 1:
            _prompt_disambiguation(ctx, "take", query, [item for _, item in matches])
            return

        room_item, item = matches[0]
        if not item.takeable:
            ctx.say("You can't take that.")
            return

        self._remove_from_room_and_carry(ctx, room_item, item, 1)
        ctx.say(f"You take {item.name}.")
        ctx.tell_room(f"{ctx.player.username} takes {item.name}.")
        self._emit_item_taken(ctx, item.id, count=1)

    def _take_quantity(
        self, target: ItemTarget, ctx: GameContext, *, take_all: bool
    ) -> None:
        matches = ctx.item_repo.search_in_room(ctx.room.id, target.query)
        if not matches:
            ctx.say("You don't see that here.")
            return

        if len(matches) > 1:
            _prompt_disambiguation(
                ctx,
                "take",
                target.query,
                [item for _, item in matches],
            )
            return

        room_item, item = matches[0]
        if not item.takeable:
            ctx.say("You can't take that.")
            return

        available = room_item.quantity
        count = available if take_all else min(target.quantity, available)
        if count <= 0:
            ctx.say("You don't see that here.")
            return

        self._remove_from_room_and_carry(ctx, room_item, item, count)
        label = format_inventory_entry(item.name, count)
        ctx.say(f"You take {label}.")
        ctx.tell_room(f"{ctx.player.username} takes {label}.")
        self._emit_item_taken(ctx, item.id, count=count)

    def _take_indexed(self, target: ItemTarget, ctx: GameContext) -> None:
        expanded = ctx.item_repo.expanded_room_instances(ctx.room.id, target.query)
        if not expanded:
            ctx.say("You don't see that here.")
            return

        if target.index is None or target.index < 1 or target.index > len(expanded):
            ctx.say("You don't see that here.")
            return

        room_item, item = expanded[target.index - 1]
        if not item.takeable:
            ctx.say("You can't take that.")
            return

        self._remove_from_room_and_carry(ctx, room_item, item, 1)
        ctx.say(f"You take {item.name}.")
        ctx.tell_room(f"{ctx.player.username} takes {item.name}.")
        self._emit_item_taken(ctx, item.id, count=1)

    def _drop_one(self, query: str, ctx: GameContext) -> None:
        matches = ctx.item_repo.search_player_items(ctx.player.inventory, query)
        if not matches:
            ctx.say("You don't have that.")
            return

        if len(matches) > 1:
            _prompt_disambiguation(ctx, "drop", query, matches)
            return

        slots = ctx.item_repo.inventory_slots_matching(ctx.player.inventory, query)
        if not slots:
            ctx.say("You don't have that.")
            return

        item = matches[0]
        self._remove_from_inventory_slots(ctx, [slots[0][0]], item, 1)
        ctx.say(f"You drop {item.name}.")
        ctx.tell_room(f"{ctx.player.username} drops {item.name}.")
        self._emit_item_dropped(ctx, item.id, count=1)

    def _drop_quantity(
        self, target: ItemTarget, ctx: GameContext, *, drop_all: bool
    ) -> None:
        slots = ctx.item_repo.inventory_slots_matching(
            ctx.player.inventory, target.query
        )
        if not slots:
            ctx.say("You don't have that.")
            return

        unique_items = _unique_items([slot_item for _, slot_item in slots])
        if len(unique_items) > 1:
            _prompt_disambiguation(ctx, "drop", target.query, unique_items)
            return

        count = len(slots) if drop_all else min(target.quantity, len(slots))
        item = slots[0][1]
        indices = [index for index, _ in slots[:count]]
        self._remove_from_inventory_slots(ctx, indices, item, count)
        label = format_inventory_entry(item.name, count)
        ctx.say(f"You drop {label}.")
        ctx.tell_room(f"{ctx.player.username} drops {label}.")
        self._emit_item_dropped(ctx, item.id, count=count)

    def _drop_indexed(self, target: ItemTarget, ctx: GameContext) -> None:
        slots = ctx.item_repo.inventory_slots_matching(
            ctx.player.inventory, target.query
        )
        if not slots:
            ctx.say("You don't have that.")
            return

        if target.index is None or target.index < 1 or target.index > len(slots):
            ctx.say("You don't have that.")
            return

        inv_index, item = slots[target.index - 1]
        self._remove_from_inventory_slots(ctx, [inv_index], item, 1)
        ctx.say(f"You drop {item.name}.")
        ctx.tell_room(f"{ctx.player.username} drops {item.name}.")
        self._emit_item_dropped(ctx, item.id, count=1)

    def _remove_from_room_and_carry(
        self,
        ctx: GameContext,
        room_item: RoomItem,
        item: Item,
        count: int,
    ) -> None:
        ctx.item_repo.remove_from_room(room_item, count)
        ctx.player.inventory = [
            *ctx.player.inventory,
            *([item.id] * count),
        ]
        ctx.push_update("inventory", list(ctx.player.inventory))

    def _remove_from_inventory_slots(
        self,
        ctx: GameContext,
        indices: list[int],
        item: Item,
        count: int,
    ) -> None:
        inventory = list(ctx.player.inventory)
        for index in sorted(indices, reverse=True):
            inventory.pop(index)
        ctx.player.inventory = inventory
        ctx.item_repo.increment_room_item(ctx.room.id, item.id, quantity=count)
        ctx.push_update("inventory", list(ctx.player.inventory))

    def _emit_item_taken(self, ctx: GameContext, item_id: str, *, count: int) -> None:
        for _ in range(count):
            ctx.queue_event(
                GameEvent.ITEM_TAKEN,
                player_id=ctx.player.id,
                room_id=ctx.room.id,
                item_id=item_id,
            )

    def _emit_item_dropped(self, ctx: GameContext, item_id: str, *, count: int) -> None:
        for _ in range(count):
            ctx.queue_event(
                GameEvent.ITEM_DROPPED,
                player_id=ctx.player.id,
                room_id=ctx.room.id,
                item_id=item_id,
            )


def room_items_visible_labels(
    room_id: str,
    get_room_items: Callable[[str], Sequence[tuple[RoomItem, Item]]],
) -> list[str]:
    """Grouped item labels for room UI panels."""
    room_items = list(get_room_items(room_id))
    if not room_items:
        return []
    return sorted(
        format_inventory_entry(item.name, room_item.quantity)
        for room_item, item in room_items
    )


def _unique_items(items: Sequence[Item]) -> list[Item]:
    seen: set[str] = set()
    unique: list[Item] = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        unique.append(item)
    return unique


def _prompt_disambiguation(
    ctx: GameContext, verb: str, noun: str, items: list[Item]
) -> None:
    options = ", ".join(f"({i + 1}) {item.name}" for i, item in enumerate(items))
    ctx.say(f"Which do you mean? {options}")
    ctx.push_update(
        "disambig_pending",
        {"verb": verb, "noun": noun, "choices": [item.name for item in items]},
    )
