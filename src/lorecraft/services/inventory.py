"""Inventory and room-item service behavior."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from lorecraft.game.command_patterns import (
    ROLE_DESTINATION,
    ROLE_INSTRUMENT,
    ROLE_RECIPIENT,
    ROLE_TARGET,
    role_str,
)
from lorecraft.game.context import GameContext
from lorecraft.game.events import GameEvent
from lorecraft.game.holders import Location
from lorecraft.models.items import ItemInstance, ItemStack
from lorecraft.models.world import Item
from lorecraft.services.item_components import get_component_state, set_component_state
from lorecraft.types import JsonValue

_M = TypeVar("_M")


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


def format_inventory_summary(stacks: Sequence[tuple[ItemStack, Item]]) -> str:
    """Comma-separated inventory list with grouped quantities."""
    labels = [
        format_inventory_entry(item.name, stack.quantity) for stack, item in stacks
    ]
    return ", ".join(labels)


def format_room_items_summary(
    room_items: Sequence[tuple[ItemStack, Item]],
) -> str:
    """Comma-separated room item list with grouped quantities."""
    labels = [
        format_inventory_entry(item.name, stack.quantity) for stack, item in room_items
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
    if lowered in {"all", "everything"}:
        return ItemTarget(query="", take_all=True)
    if lowered.startswith("all "):
        return ItemTarget(query=text[4:].strip(), take_all=True)
    if lowered.startswith("everything "):
        return ItemTarget(query=text[len("everything ") :].strip(), take_all=True)

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
    def _resolve_single(
        self,
        ctx: GameContext,
        *,
        verb: str,
        query: str,
        matches: Sequence[_M],
        item_of: Callable[[_M], Item],
        not_found_msg: str,
    ) -> _M | None:
        """Shared find→disambiguate step for a pre-resolved match list.

        Returns the single match, or ``None`` after messaging the player
        (either a "not found" message or a numbered disambiguation prompt).
        """
        if not matches:
            ctx.say(not_found_msg)
            return None
        if len(matches) > 1:
            _prompt_disambiguation(ctx, verb, query, [item_of(m) for m in matches])
            return None
        return matches[0]

    def _do_take(
        self, ctx: GameContext, stack: ItemStack, item: Item, count: int
    ) -> None:
        self._move_room_to_player(ctx, stack, count)
        label = format_inventory_entry(item.name, count)
        ctx.say(f"You take {label}.")
        ctx.tell_room(f"{ctx.player.username} takes {label}.")
        self._emit_item_taken(ctx, item.id, count=count)

    def _do_drop(
        self, ctx: GameContext, stack: ItemStack, item: Item, count: int
    ) -> None:
        self._move_player_to_room(ctx, stack, count)
        label = format_inventory_entry(item.name, count)
        ctx.say(f"You drop {label}.")
        ctx.tell_room(f"{ctx.player.username} drops {label}.")
        self._emit_item_dropped(ctx, item.id, count=count)

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

        room_items = ctx.item_repo.items_in_room(ctx.room.id)
        if room_items:
            summary = format_room_items_summary(room_items)
            ctx.say(f"You see: {summary}.")

        ctx.push_update("room_id", ctx.room.id)

    def inventory(self, ctx: GameContext) -> None:
        stacks = ctx.item_repo.stacks_carried_by(ctx.player.id)
        if not stacks:
            ctx.say("You are carrying nothing.")
            ctx.push_update("inventory", [])
            return

        summary = format_inventory_summary(stacks)
        ctx.say(f"You are carrying: {summary}.")
        ctx.push_update("inventory", inventory_update_entries(stacks))

    def examine(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            self.look(ctx)
            return

        all_matches = self._find_carried_or_visible(name_or_id, ctx)
        match = self._resolve_single(
            ctx,
            verb="examine",
            query=name_or_id,
            matches=all_matches,
            item_of=lambda item: item,
            not_found_msg="You don't see that here.",
        )
        if match is None:
            return
        ctx.say(match.description)

    def take_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Take what?")
            return

        target = parse_item_target(name_or_id)
        if target.index is not None:
            self._take_indexed(target, ctx)
            return
        if target.take_all:
            if not target.query:
                self._take_everything_in_room(ctx)
                return
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

    def _take_everything_in_room(self, ctx: GameContext) -> None:
        room_items = ctx.item_repo.items_in_room(ctx.room.id)
        if not room_items:
            ctx.say("There is nothing here to take.")
            return

        taken_labels: list[str] = []
        for stack, item in room_items:
            if not item.takeable:
                continue
            count = stack.quantity
            if count <= 0:
                continue
            self._move_room_to_player(ctx, stack, count)
            taken_labels.append(format_inventory_entry(item.name, count))
            self._emit_item_taken(ctx, item.id, count=count)

        if not taken_labels:
            ctx.say("There is nothing here you can take.")
            return

        summary = ", ".join(taken_labels)
        ctx.say(f"You take {summary}.")
        ctx.tell_room(f"{ctx.player.username} takes {summary}.")

    def _take_one(self, query: str, ctx: GameContext) -> None:
        matches = ctx.item_repo.search_in_room(ctx.room.id, query)
        match = self._resolve_single(
            ctx,
            verb="take",
            query=query,
            matches=matches,
            item_of=lambda m: m[1],
            not_found_msg="You don't see that here.",
        )
        if match is None:
            return

        stack, item = match
        if not item.takeable:
            ctx.say("You can't take that.")
            return

        self._do_take(ctx, stack, item, 1)

    def _take_quantity(
        self, target: ItemTarget, ctx: GameContext, *, take_all: bool
    ) -> None:
        matches = ctx.item_repo.search_in_room(ctx.room.id, target.query)
        match = self._resolve_single(
            ctx,
            verb="take",
            query=target.query,
            matches=matches,
            item_of=lambda m: m[1],
            not_found_msg="You don't see that here.",
        )
        if match is None:
            return

        stack, item = match
        if not item.takeable:
            ctx.say("You can't take that.")
            return

        available = stack.quantity
        count = available if take_all else min(target.quantity, available)
        if count <= 0:
            ctx.say("You don't see that here.")
            return

        self._do_take(ctx, stack, item, count)

    def _take_indexed(self, target: ItemTarget, ctx: GameContext) -> None:
        expanded = ctx.item_repo.expanded_room_instances(ctx.room.id, target.query)
        if (
            not expanded
            or target.index is None
            or not (1 <= target.index <= len(expanded))
        ):
            ctx.say("You don't see that here.")
            return

        stack, item = expanded[target.index - 1]
        if not item.takeable:
            ctx.say("You can't take that.")
            return

        self._do_take(ctx, stack, item, 1)

    def _drop_one(self, query: str, ctx: GameContext) -> None:
        matches = ctx.item_repo.search_player_items(ctx.player.id, query)
        match = self._resolve_single(
            ctx,
            verb="drop",
            query=query,
            matches=matches,
            item_of=lambda item: item,
            not_found_msg="You don't have that.",
        )
        if match is None:
            return

        stacks = ctx.item_repo.player_stacks_matching(ctx.player.id, query)
        if not stacks:
            ctx.say("You don't have that.")
            return

        self._do_drop(ctx, stacks[0][0], match, 1)

    def _drop_quantity(
        self, target: ItemTarget, ctx: GameContext, *, drop_all: bool
    ) -> None:
        stacks = ctx.item_repo.player_stacks_matching(ctx.player.id, target.query)
        if not stacks:
            ctx.say("You don't have that.")
            return

        unique_items = _unique_items([item for _, item in stacks])
        match = self._resolve_single(
            ctx,
            verb="drop",
            query=target.query,
            matches=unique_items,
            item_of=lambda item: item,
            not_found_msg="You don't have that.",
        )
        if match is None:
            return

        available = sum(stack.quantity for stack, _ in stacks)
        count = available if drop_all else min(target.quantity, available)
        remaining = count
        for stack, _ in stacks:
            if remaining <= 0:
                break
            take_from_stack = min(remaining, stack.quantity)
            self._move_player_to_room(ctx, stack, take_from_stack)
            remaining -= take_from_stack

        label = format_inventory_entry(match.name, count)
        ctx.say(f"You drop {label}.")
        ctx.tell_room(f"{ctx.player.username} drops {label}.")
        self._emit_item_dropped(ctx, match.id, count=count)

    def _drop_indexed(self, target: ItemTarget, ctx: GameContext) -> None:
        expanded = ctx.item_repo.expanded_player_instances(ctx.player.id, target.query)
        if (
            not expanded
            or target.index is None
            or not (1 <= target.index <= len(expanded))
        ):
            ctx.say("You don't have that.")
            return

        stack, item = expanded[target.index - 1]
        self._do_drop(ctx, stack, item, 1)

    def _move_room_to_player(
        self, ctx: GameContext, stack: ItemStack, count: int
    ) -> None:
        assert stack.id is not None
        ctx.item_location.move(stack.id, Location("player", ctx.player.id), count)
        ctx.push_update(
            "inventory",
            inventory_update_entries(ctx.item_repo.stacks_carried_by(ctx.player.id)),
        )

    def _move_player_to_room(
        self, ctx: GameContext, stack: ItemStack, count: int
    ) -> None:
        assert stack.id is not None
        ctx.item_location.move(stack.id, Location("room", ctx.room.id), count)
        ctx.push_update(
            "inventory",
            inventory_update_entries(ctx.item_repo.stacks_carried_by(ctx.player.id)),
        )

    def use_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Use what?")
            return

        matches = self._find_carried_or_visible(name_or_id, ctx)
        item = self._resolve_single(
            ctx,
            verb="use",
            query=name_or_id,
            matches=matches,
            item_of=lambda m: m,
            not_found_msg="You don't have that.",
        )
        if item is None:
            return

        other_phrase = _use_target_phrase(ctx)
        if other_phrase is None:
            if item.usable_with:
                ctx.say(f"You need to use the {item.name} with something specific.")
            else:
                ctx.say(f"You use the {item.name}, but nothing happens.")
            self._emit_item_used(ctx, item.id)
            return

        other_matches = self._find_carried_or_visible(other_phrase, ctx)
        if not other_matches:
            ctx.say(f"You don't see {other_phrase} here.")
            return
        if len(other_matches) > 1:
            names = ", ".join(sorted({other.name for other in other_matches}))
            ctx.say(f"Which do you mean: {names}?")
            return

        other = other_matches[0]
        if _items_combine(item, other):
            ctx.say(f"You use the {item.name} with the {other.name}. It works!")
            ctx.tell_room(f"{ctx.player.username} uses {item.name} with {other.name}.")
        else:
            ctx.say(f"Using the {item.name} with the {other.name} does nothing.")

        self._emit_item_used(ctx, item.id, other_item_id=other.id)

    def give_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Give what?")
            return

        parsed = ctx.parsed_command
        recipient_phrase = role_str(parsed, ROLE_RECIPIENT) if parsed else None
        if not recipient_phrase:
            ctx.say("Give it to whom?")
            return

        npc = ctx.npc_repo.find_in_room(ctx.room.id, recipient_phrase)
        if npc is None:
            ctx.say(f"There is no {recipient_phrase} here.")
            return

        matches = ctx.item_repo.search_player_items(ctx.player.id, name_or_id)
        item = self._resolve_single(
            ctx,
            verb="give",
            query=name_or_id,
            matches=matches,
            item_of=lambda m: m,
            not_found_msg="You don't have that.",
        )
        if item is None:
            return

        stacks = ctx.item_repo.player_stacks_matching(ctx.player.id, name_or_id)
        if not stacks:
            ctx.say("You don't have that.")
            return

        stack = stacks[0][0]
        assert stack.id is not None
        ctx.item_location.destroy(stack.id, 1)
        ctx.push_update(
            "inventory",
            inventory_update_entries(ctx.item_repo.stacks_carried_by(ctx.player.id)),
        )
        ctx.say(f"You give the {item.name} to {npc.name}.")
        ctx.tell_room(f"{ctx.player.username} gives {item.name} to {npc.name}.")
        ctx.queue_event(
            GameEvent.ITEM_GIVEN,
            player_id=ctx.player.id,
            room_id=ctx.room.id,
            item_id=item.id,
            npc_id=npc.id,
        )

    def _find_carried_or_visible(self, query: str, ctx: GameContext) -> list[Item]:
        inv_matches = ctx.item_repo.search_player_items(ctx.player.id, query)
        room_matches = [
            item for _, item in ctx.item_repo.search_in_room(ctx.room.id, query)
        ]
        seen: set[str] = set()
        combined: list[Item] = []
        for candidate in inv_matches + room_matches:
            if candidate.id not in seen:
                seen.add(candidate.id)
                combined.append(candidate)
        return combined

    def _find_carried_or_visible_stacks(
        self, query: str, ctx: GameContext
    ) -> list[tuple[ItemStack, Item]]:
        carried = ctx.item_repo.player_stacks_matching(ctx.player.id, query)
        room = ctx.item_repo.search_in_room(ctx.room.id, query)
        return list(carried) + list(room)

    def _resolve_openable(
        self, query: str, ctx: GameContext, *, verb: str
    ) -> tuple[Item, ItemInstance] | None:
        matches = self._find_carried_or_visible_stacks(query, ctx)
        resolved = self._resolve_single(
            ctx,
            verb=verb,
            query=query,
            matches=matches,
            item_of=lambda m: m[1],
            not_found_msg="You don't see that here.",
        )
        if resolved is None:
            return None

        stack, item = resolved
        if stack.instance_id is None:
            ctx.say(f"You can't {verb} that.")
            return None

        instance = ctx.session.get(ItemInstance, stack.instance_id)
        if instance is None or get_component_state(instance, "openable") is None:
            ctx.say(f"You can't {verb} that.")
            return None

        return item, instance

    def open_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Open what?")
            return

        resolved = self._resolve_openable(name_or_id, ctx, verb="open")
        if resolved is None:
            return
        item, instance = resolved

        state = get_component_state(instance, "openable")
        if isinstance(state, dict) and state.get("open"):
            ctx.say(f"The {item.name} is already open.")
            return

        set_component_state(ctx.session, instance, "openable", {"open": True})
        ctx.say(f"You open the {item.name}.")
        ctx.tell_room(f"{ctx.player.username} opens the {item.name}.")

    def close_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Close what?")
            return

        resolved = self._resolve_openable(name_or_id, ctx, verb="close")
        if resolved is None:
            return
        item, instance = resolved

        state = get_component_state(instance, "openable")
        if isinstance(state, dict) and not state.get("open"):
            ctx.say(f"The {item.name} is already closed.")
            return

        set_component_state(ctx.session, instance, "openable", {"open": False})
        ctx.say(f"You close the {item.name}.")
        ctx.tell_room(f"{ctx.player.username} closes the {item.name}.")

    def _emit_item_used(
        self, ctx: GameContext, item_id: str, *, other_item_id: str | None = None
    ) -> None:
        payload: dict[str, JsonValue] = {
            "player_id": ctx.player.id,
            "room_id": ctx.room.id,
            "item_id": item_id,
        }
        if other_item_id is not None:
            payload["other_item_id"] = other_item_id
        ctx.queue_event(GameEvent.ITEM_USED, **payload)

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


def inventory_update_entries(stacks: Sequence[tuple[ItemStack, Item]]) -> JsonValue:
    """Build the inventory WS/HTMX push payload: one entry (an InventoryEntry
    shape, see types.py) per carried stack."""
    return [
        {
            "item_id": item.id,
            "name": item.name,
            "quantity": stack.quantity,
            "instance_id": stack.instance_id,
        }
        for stack, item in stacks
    ]


def room_items_visible_labels(
    room_id: str,
    get_room_items: Callable[[str], Sequence[tuple[ItemStack, Item]]],
) -> list[str]:
    """Grouped item labels for room UI panels."""
    room_items = list(get_room_items(room_id))
    if not room_items:
        return []
    return sorted(
        format_inventory_entry(item.name, stack.quantity) for stack, item in room_items
    )


def _use_target_phrase(ctx: GameContext) -> str | None:
    """Secondary role for ``use <item> on/with <other>`` from the parsed command."""
    parsed = ctx.parsed_command
    if parsed is None:
        return None
    return (
        role_str(parsed, ROLE_DESTINATION)
        or role_str(parsed, ROLE_INSTRUMENT)
        or role_str(parsed, ROLE_TARGET)
    )


def _items_combine(item: Item, other: Item) -> bool:
    return other.id in item.usable_with or item.id in other.usable_with


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
