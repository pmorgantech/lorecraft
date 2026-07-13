"""Inventory and room-item service behavior."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from lorecraft.errors import ConflictError, ValidationError
from lorecraft.engine.game.command_patterns import (
    ROLE_DESTINATION,
    ROLE_INSTRUMENT,
    ROLE_RECIPIENT,
    ROLE_SOURCE,
    ROLE_TARGET,
    role_str,
)
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.features.encumbrance.rules import (
    encumbrance_band,
    resolve_carry_capacity,
    total_carried_weight,
)
from lorecraft.features.equipment.slots import FINGER_SLOTS, slot_label
from lorecraft.engine.game.events import GameEvent
from lorecraft.features.exploration.rules import is_exit_discovered
from lorecraft.engine.game.holders import Location
from lorecraft.features.terrain import definitions as terrain_module
from lorecraft.engine.models.items import ItemInstance, ItemStack
from lorecraft.engine.models.world import Item
from lorecraft.engine.services.item_components import (
    get_component_state,
    set_component_state,
)
from lorecraft.features.inventory.look_pure import (
    ATTR_DESCRIPTION,
    ATTR_EXITS,
    ATTR_NAME,
    ATTR_TERRAIN_SUFFIX,
    ITEM_ATTR_NAME,
    ITEM_ATTR_QUANTITY,
    look_effects,
)
from lorecraft.protocol import (
    EntitySnapshot,
    Feed,
    PanelUpdate,
    ScriptBudget,
    ScriptRequest,
)
from lorecraft.protocol.version import PROTOCOL_VERSION
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
            ctx.say(not_found_msg, MessageType.WARNING)
            return None
        if len(matches) > 1:
            _prompt_disambiguation(ctx, verb, query, [item_of(m) for m in matches])
            return None
        return matches[0]

    def find_carried_item(
        self, query: str, ctx: GameContext, *, verb: str
    ) -> tuple[ItemStack, Item] | None:
        """Resolve one *carried* (loose) item + its stack, or ``None`` after
        messaging the player. Shared find→disambiguate step reused by verbs that
        act on a held item (e.g. eat/drink in the consumables feature), mirroring
        the resolution `give_item` does inline."""
        matches = ctx.item_repo.search_player_items(ctx.player.id, query)
        item = self._resolve_single(
            ctx,
            verb=verb,
            query=query,
            matches=matches,
            item_of=lambda m: m,
            not_found_msg="You don't have that.",
        )
        if item is None:
            return None
        stacks = ctx.item_repo.player_stacks_matching(ctx.player.id, query)
        loose = [stack for stack, candidate in stacks if candidate.id == item.id]
        if not loose:
            ctx.say("You don't have that.", MessageType.WARNING)
            return None
        return loose[0], item

    def _do_take(
        self, ctx: GameContext, stack: ItemStack, item: Item, count: int
    ) -> None:
        if self._would_overload(ctx, item, count):
            ctx.say("You can't carry any more weight.", MessageType.WARNING)
            return
        self._move_room_to_player(ctx, stack, count)
        label = format_inventory_entry(item.name, count)
        ctx.say(f"You take {label}.")
        ctx.tell_room(f"{ctx.player.username} takes {label}.")
        self._emit_item_taken(ctx, item.id, count=count)

    def _would_overload(self, ctx: GameContext, item: Item, count: int) -> bool:
        if item.weight <= 0:
            return False
        stats = ctx.player_repo.stats(ctx.player.id)
        strength = stats.strength if stats is not None else 10
        capacity = resolve_carry_capacity(ctx.session, ctx.player.id, strength)
        current = total_carried_weight(ctx.session, ctx.player.id)
        projected = current + item.weight * count
        return encumbrance_band(projected, capacity) == "overloaded"

    def _do_drop(
        self, ctx: GameContext, stack: ItemStack, item: Item, count: int
    ) -> None:
        self._move_player_to_room(ctx, stack, count)
        label = format_inventory_entry(item.name, count)
        ctx.say(f"You drop {label}.")
        ctx.tell_room(f"{ctx.player.username} drops {label}.")
        self._emit_item_dropped(ctx, item.id, count=count)

    def look(self, ctx: GameContext) -> None:
        """Thin shim over the pure `look_effects` policy: read the same world
        state it always has (room, visible exits, terrain suffix, room items)
        into an immutable `ScriptRequest`, then apply the returned messages the
        old way. No behavior change — the ordering/formatting lives in
        `look_pure.look_effects`."""
        request = self._build_look_request(ctx)
        result = look_effects(request)
        for message in result.messages:
            if isinstance(message, Feed):
                ctx.say(message.text, MessageType(message.message_type))
            elif isinstance(message, PanelUpdate):
                ctx.push_update(message.key, message.value)

    def _build_look_request(self, ctx: GameContext) -> ScriptRequest:
        """Materialize the read-only room snapshot `look_effects` consumes."""
        terrain_def = terrain_module.get_registry().get(ctx.room.terrain)
        terrain_suffix = (
            terrain_def.description_suffix
            if terrain_def is not None and terrain_def.description_suffix
            else None
        )
        visible_exits = [
            exit_.direction
            for exit_ in ctx.room_repo.exits(ctx.room.id)
            if not exit_.hidden or is_exit_discovered(ctx, ctx.room.id, exit_.direction)
        ]
        room_snapshot = EntitySnapshot(
            id=ctx.room.id,
            kind="room",
            attributes={
                ATTR_NAME: ctx.room.name,
                ATTR_DESCRIPTION: ctx.room.description,
                ATTR_TERRAIN_SUFFIX: terrain_suffix,
                ATTR_EXITS: list(visible_exits),
            },
        )
        related = [
            EntitySnapshot(
                id=item.id,
                kind="item",
                attributes={
                    ITEM_ATTR_NAME: item.name,
                    ITEM_ATTR_QUANTITY: stack.quantity,
                },
            )
            for stack, item in ctx.item_repo.items_in_room(ctx.room.id)
        ]
        actor_snapshot = EntitySnapshot(id=ctx.player.id, kind="player", attributes={})
        return ScriptRequest(
            api_version=PROTOCOL_VERSION,
            script_id="look",
            script_version=1,
            command_or_event="look",
            actor_snapshot=actor_snapshot,
            room_snapshot=room_snapshot,
            selected_related_entities=related,
            logical_time=0,
            rng_stream_id="",
            capability_set=[],
            budget=ScriptBudget(
                wall_ms=0, instructions=0, memory_bytes=0, output_bytes=0
            ),
        )

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
        _record_item_discovery(ctx, match.id)

    def take_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Take what?", MessageType.WARNING)
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
            ctx.say("Drop what?", MessageType.WARNING)
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
            ctx.say("There is nothing here to take.", MessageType.WARNING)
            return

        taken_labels: list[str] = []
        for stack, item in room_items:
            if not item.takeable:
                continue
            count = stack.quantity
            if count <= 0:
                continue
            if self._would_overload(ctx, item, count):
                continue
            self._move_room_to_player(ctx, stack, count)
            taken_labels.append(format_inventory_entry(item.name, count))
            self._emit_item_taken(ctx, item.id, count=count)

        if not taken_labels:
            ctx.say("There is nothing here you can take.", MessageType.WARNING)
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
            ctx.say("You can't take that.", MessageType.WARNING)
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
            ctx.say("You can't take that.", MessageType.WARNING)
            return

        available = stack.quantity
        count = available if take_all else min(target.quantity, available)
        if count <= 0:
            ctx.say("You don't see that here.", MessageType.WARNING)
            return

        self._do_take(ctx, stack, item, count)

    def _take_indexed(self, target: ItemTarget, ctx: GameContext) -> None:
        expanded = ctx.item_repo.expanded_room_instances(ctx.room.id, target.query)
        if (
            not expanded
            or target.index is None
            or not (1 <= target.index <= len(expanded))
        ):
            ctx.say("You don't see that here.", MessageType.WARNING)
            return

        stack, item = expanded[target.index - 1]
        if not item.takeable:
            ctx.say("You can't take that.", MessageType.WARNING)
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
            ctx.say("You don't have that.", MessageType.WARNING)
            return

        self._do_drop(ctx, stacks[0][0], match, 1)

    def _drop_quantity(
        self, target: ItemTarget, ctx: GameContext, *, drop_all: bool
    ) -> None:
        stacks = ctx.item_repo.player_stacks_matching(ctx.player.id, target.query)
        if not stacks:
            ctx.say("You don't have that.", MessageType.WARNING)
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
            ctx.say("You don't have that.", MessageType.WARNING)
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
            ctx.say("Use what?", MessageType.WARNING)
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
                ctx.say(
                    f"You need to use the {item.name} with something specific.",
                    MessageType.WARNING,
                )
            else:
                ctx.say(
                    f"You use the {item.name}, but nothing happens.",
                    MessageType.WARNING,
                )
            self._emit_item_used(ctx, item.id)
            return

        other_matches = self._find_carried_or_visible(other_phrase, ctx)
        if not other_matches:
            ctx.say(f"You don't see {other_phrase} here.", MessageType.WARNING)
            return
        if len(other_matches) > 1:
            names = ", ".join(sorted({other.name for other in other_matches}))
            ctx.say(f"Which do you mean: {names}?", MessageType.WARNING)
            return

        other = other_matches[0]
        if _items_combine(item, other):
            ctx.say(f"You use the {item.name} with the {other.name}. It works!")
            ctx.tell_room(f"{ctx.player.username} uses {item.name} with {other.name}.")
            self._apply_combination_side_effects(item, other, ctx)
        else:
            ctx.say(
                f"Using the {item.name} with the {other.name} does nothing.",
                MessageType.WARNING,
            )

        self._emit_item_used(ctx, item.id, other_item_id=other.id)

    def _apply_combination_side_effects(
        self, item: Item, other: Item, ctx: GameContext
    ) -> None:
        """Sprint 30.2: a successful `use X with Y` can be more than flavor
        text -- checked in both authoring directions (checking `item`'s dict
        first) since a combination only needs one side to declare the
        consequence."""
        effects = item.combination_side_effects.get(
            other.id
        ) or other.combination_side_effects.get(item.id)
        if isinstance(effects, dict):
            from lorecraft.features.npc.side_effects import get_registry

            get_registry().apply(effects, ctx)

    def give_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Give what?", MessageType.WARNING)
            return

        parsed = ctx.parsed_command
        recipient_phrase = role_str(parsed, ROLE_RECIPIENT) if parsed else None
        if not recipient_phrase:
            ctx.say("Give it to whom?", MessageType.WARNING)
            return

        npc = ctx.npc_repo.find_in_room(ctx.room.id, recipient_phrase)
        if npc is None:
            ctx.say(f"There is no {recipient_phrase} here.", MessageType.WARNING)
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
            ctx.say("You don't have that.", MessageType.WARNING)
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

    def _equipped_stacks(self, ctx: GameContext) -> list[tuple[ItemStack, Item]]:
        result: list[tuple[ItemStack, Item]] = []
        for stack in ctx.stack_repo.stacks_for_owner("player", ctx.player.id):
            if stack.slot is None:
                continue
            item = ctx.item_repo.get(stack.item_id)
            if item is not None:
                result.append((stack, item))
        return result

    def _query_matches_item(self, query: str, item: Item) -> bool:
        q = query.strip().casefold()
        if q == item.name.casefold() or q == item.id.casefold():
            return True
        q_words = set(q.split())
        name_words = set(item.name.casefold().split())
        return bool(q_words) and q_words.issubset(name_words)

    def wear_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Wear what?", MessageType.WARNING)
            return
        self._equip(name_or_id, ctx, verb="wear", wearable=True)

    def wield_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Wield what?", MessageType.WARNING)
            return
        self._equip(name_or_id, ctx, verb="wield", wearable=False)

    def _equip(
        self, name_or_id: str, ctx: GameContext, *, verb: str, wearable: bool
    ) -> None:
        matches = ctx.item_repo.search_player_items(ctx.player.id, name_or_id)
        item = self._resolve_single(
            ctx,
            verb=verb,
            query=name_or_id,
            matches=matches,
            item_of=lambda m: m,
            not_found_msg="You don't have that.",
        )
        if item is None:
            return

        if item.wearable != wearable:
            ctx.say(f"You can't {verb} the {item.name}.", MessageType.WARNING)
            return

        if item.slot is None:
            ctx.say(f"The {item.name} has no equip slot.", MessageType.WARNING)
            return

        stacks = ctx.item_repo.player_stacks_matching(ctx.player.id, name_or_id)
        loose_stacks = [s for s, _ in stacks if s.slot is None]
        if not loose_stacks:
            ctx.say(f"You aren't carrying a loose {item.name}.", MessageType.WARNING)
            return
        stack = loose_stacks[0]

        target_slot = self._resolve_target_slot(ctx, item)
        if target_slot is None:
            return

        assert stack.id is not None
        try:
            ctx.item_location.move(
                stack.id, Location("player", ctx.player.id, slot=target_slot), 1
            )
        except (ValidationError, ConflictError) as exc:
            ctx.say(exc.message, MessageType.WARNING)
            return

        ctx.say(f"You {verb} the {item.name}.")
        ctx.tell_room(f"{ctx.player.username} {verb}s the {item.name}.")
        ctx.queue_event(
            GameEvent.ITEM_EQUIPPED,
            player_id=ctx.player.id,
            item_id=item.id,
            slot=target_slot,
        )
        self._push_equipment_update(ctx)

    def _resolve_target_slot(self, ctx: GameContext, item: Item) -> str | None:
        if item.slot != "finger":
            assert item.slot is not None
            return item.slot
        for slot in FINGER_SLOTS:
            if not ctx.stack_repo.stacks_at(
                Location("player", ctx.player.id, slot=slot)
            ):
                return slot
        ctx.say("Both your finger slots are full.", MessageType.WARNING)
        return None

    def remove_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Remove what?", MessageType.WARNING)
            return
        self._unequip(name_or_id, ctx, verb="remove")

    def unwield_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Unwield what?", MessageType.WARNING)
            return
        self._unequip(name_or_id, ctx, verb="unwield")

    def _unequip(self, name_or_id: str, ctx: GameContext, *, verb: str) -> None:
        equipped = self._equipped_stacks(ctx)
        matching = [
            (stack, item)
            for stack, item in equipped
            if self._query_matches_item(name_or_id, item)
        ]
        if not matching:
            ctx.say("You aren't wearing or wielding that.", MessageType.WARNING)
            return
        if len(matching) > 1:
            _prompt_disambiguation(
                ctx, verb, name_or_id, [item for _, item in matching]
            )
            return

        stack, item = matching[0]
        assert stack.id is not None
        ctx.item_location.move(stack.id, Location("player", ctx.player.id), 1)
        ctx.say(f"You {verb} the {item.name}.")
        ctx.tell_room(f"{ctx.player.username} {verb}s the {item.name}.")
        ctx.queue_event(
            GameEvent.ITEM_UNEQUIPPED,
            player_id=ctx.player.id,
            item_id=item.id,
            slot=stack.slot,
        )
        self._push_equipment_update(ctx)

    def list_equipment(self, ctx: GameContext) -> None:
        equipped = self._equipped_stacks(ctx)
        if not equipped:
            ctx.say("You aren't wearing or wielding anything.", MessageType.WARNING)
            ctx.push_update("equipment", [])
            return

        ctx.say("You are equipped with:")
        for stack, item in sorted(equipped, key=lambda pair: pair[0].slot or ""):
            ctx.say(f"  {slot_label(stack.slot)}: {item.name}")
        self._push_equipment_update(ctx)

    def _push_equipment_update(self, ctx: GameContext) -> None:
        equipped = self._equipped_stacks(ctx)
        ctx.push_update(
            "equipment",
            [
                {"slot": stack.slot, "item_id": item.id, "name": item.name}
                for stack, item in equipped
            ],
        )

    def put_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Put what?", MessageType.WARNING)
            return

        parsed = ctx.parsed_command
        container_phrase = role_str(parsed, ROLE_DESTINATION) if parsed else None
        if not container_phrase:
            ctx.say("Put it where?", MessageType.WARNING)
            return

        container_match = self._resolve_container(container_phrase, ctx, verb="put")
        if container_match is None:
            return
        _container_item, container_instance = container_match

        matches = ctx.item_repo.search_player_items(ctx.player.id, name_or_id)
        item = self._resolve_single(
            ctx,
            verb="put",
            query=name_or_id,
            matches=matches,
            item_of=lambda m: m,
            not_found_msg="You don't have that.",
        )
        if item is None:
            return

        stacks = ctx.item_repo.player_stacks_matching(ctx.player.id, name_or_id)
        loose_stacks = [s for s, _ in stacks if s.slot is None]
        if not loose_stacks:
            ctx.say("You aren't carrying that loose.", MessageType.WARNING)
            return
        stack = loose_stacks[0]

        assert stack.id is not None
        try:
            ctx.item_location.move(
                stack.id, Location("container", container_instance.id), 1
            )
        except (ValidationError, ConflictError) as exc:
            ctx.say(exc.message, MessageType.WARNING)
            return

        ctx.say(f"You put the {item.name} in the {_container_item.name}.")
        ctx.tell_room(
            f"{ctx.player.username} puts {item.name} in {_container_item.name}."
        )
        ctx.push_update(
            "inventory",
            inventory_update_entries(ctx.item_repo.stacks_carried_by(ctx.player.id)),
        )
        # A4: container effect triggers — a magic chest can react to what's placed inside.
        ctx.queue_event(
            GameEvent.ITEM_STORED,
            container_item_id=_container_item.id,
            container_instance_id=container_instance.id,
            item_id=item.id,
            player_id=ctx.player.id,
        )

    def take_from_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Take what?", MessageType.WARNING)
            return

        parsed = ctx.parsed_command
        container_phrase = role_str(parsed, ROLE_SOURCE) if parsed else None
        if not container_phrase:
            self.take_item(name_or_id, ctx)
            return

        container_match = self._resolve_container(container_phrase, ctx, verb="take")
        if container_match is None:
            return
        container_item, container_instance = container_match

        openable_state = get_component_state(container_instance, "openable")
        if isinstance(openable_state, dict) and not openable_state.get("open"):
            ctx.say(f"The {container_item.name} is closed.", MessageType.WARNING)
            return

        contents = ctx.stack_repo.stacks_at(
            Location("container", container_instance.id)
        )
        matching_stacks: list[tuple[ItemStack, Item]] = []
        for content_stack in contents:
            content_item = ctx.item_repo.get(content_stack.item_id)
            if content_item is not None and self._query_matches_item(
                name_or_id, content_item
            ):
                matching_stacks.append((content_stack, content_item))

        if not matching_stacks:
            ctx.say(
                f"There is no {name_or_id} in the {container_item.name}.",
                MessageType.WARNING,
            )
            return
        if len(matching_stacks) > 1:
            _prompt_disambiguation(
                ctx, "take", name_or_id, [item for _, item in matching_stacks]
            )
            return

        stack, item = matching_stacks[0]
        if self._would_overload(ctx, item, 1):
            ctx.say("You can't carry any more weight.", MessageType.WARNING)
            return

        assert stack.id is not None
        ctx.item_location.move(stack.id, Location("player", ctx.player.id), 1)
        ctx.say(f"You take the {item.name} from the {container_item.name}.")
        ctx.tell_room(
            f"{ctx.player.username} takes {item.name} from {container_item.name}."
        )
        ctx.push_update(
            "inventory",
            inventory_update_entries(ctx.item_repo.stacks_carried_by(ctx.player.id)),
        )
        # A4: container effect triggers — mirror of item_stored.
        ctx.queue_event(
            GameEvent.ITEM_REMOVED,
            container_item_id=container_item.id,
            container_instance_id=container_instance.id,
            item_id=item.id,
            player_id=ctx.player.id,
        )

    def _resolve_container(
        self, query: str, ctx: GameContext, *, verb: str
    ) -> tuple[Item, ItemInstance] | None:
        return self._resolve_openable(query, ctx, verb=verb)

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
        # player_stacks_matching only sees loose (slot=None) stacks — open/close/
        # light/extinguish need to find equipped items too (a wielded lantern).
        carried: list[tuple[ItemStack, Item]] = []
        for stack in ctx.stack_repo.stacks_for_owner("player", ctx.player.id):
            item = ctx.item_repo.get(stack.item_id)
            if item is not None and self._query_matches_item(query, item):
                carried.append((stack, item))
        room = ctx.item_repo.search_in_room(ctx.room.id, query)
        return carried + list(room)

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
            ctx.say(f"You can't {verb} that.", MessageType.WARNING)
            return None

        instance = ctx.session.get(ItemInstance, stack.instance_id)
        if instance is None or get_component_state(instance, "openable") is None:
            ctx.say(f"You can't {verb} that.", MessageType.WARNING)
            return None

        return item, instance

    def open_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Open what?", MessageType.WARNING)
            return

        resolved = self._resolve_openable(name_or_id, ctx, verb="open")
        if resolved is None:
            return
        item, instance = resolved

        state = get_component_state(instance, "openable")
        if isinstance(state, dict) and state.get("open"):
            ctx.say(f"The {item.name} is already open.", MessageType.WARNING)
            return

        set_component_state(ctx.session, instance, "openable", {"open": True})
        ctx.say(f"You open the {item.name}.")
        ctx.tell_room(f"{ctx.player.username} opens the {item.name}.")

    def close_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Close what?", MessageType.WARNING)
            return

        resolved = self._resolve_openable(name_or_id, ctx, verb="close")
        if resolved is None:
            return
        item, instance = resolved

        state = get_component_state(instance, "openable")
        if isinstance(state, dict) and not state.get("open"):
            ctx.say(f"The {item.name} is already closed.", MessageType.WARNING)
            return

        set_component_state(ctx.session, instance, "openable", {"open": False})
        ctx.say(f"You close the {item.name}.")
        ctx.tell_room(f"{ctx.player.username} closes the {item.name}.")

    def _resolve_mechanism(
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
            ctx.say(f"You can't {verb} that.", MessageType.WARNING)
            return None

        instance = ctx.session.get(ItemInstance, stack.instance_id)
        if instance is None or get_component_state(instance, "mechanism") is None:
            ctx.say(f"You can't {verb} that.", MessageType.WARNING)
            return None

        return item, instance

    def activate_mechanism(self, name_or_id: str | None, ctx: GameContext) -> None:
        """Sprint 30.2: cycle a lever/dial's `mechanism` component state,
        applying `Item.mechanism_side_effects[new_state]` (any handler on
        npc/side_effects.py's registry -- typically set_flags, which
        existing Exit.condition_flags/dialogue/quest gates already consume,
        so a lever "solving" is a one-way trigger, not a live "must be
        currently in state X" check."""
        if name_or_id is None:
            ctx.say("Activate what?", MessageType.WARNING)
            return

        resolved = self._resolve_mechanism(name_or_id, ctx, verb="activate")
        if resolved is None:
            return
        item, instance = resolved

        states = item.mechanism_states
        if not states:
            ctx.say(f"You can't activate the {item.name}.", MessageType.WARNING)
            return

        state = get_component_state(instance, "mechanism")
        current_index = state.get("index", 0) if isinstance(state, dict) else 0
        if not isinstance(current_index, int) or not 0 <= current_index < len(states):
            current_index = 0
        new_index = (current_index + 1) % len(states)
        new_state_name = states[new_index]

        set_component_state(ctx.session, instance, "mechanism", {"index": new_index})
        ctx.say(f"You turn the {item.name}. It clicks to '{new_state_name}'.")
        ctx.tell_room(f"{ctx.player.username} activates the {item.name}.")

        effects = item.mechanism_side_effects.get(new_state_name)
        if isinstance(effects, dict):
            from lorecraft.features.npc.side_effects import get_registry

            get_registry().apply(effects, ctx)

    def _resolve_lit_source(
        self, query: str, ctx: GameContext, *, verb: str
    ) -> tuple[Item, ItemInstance] | None:
        matches = self._find_carried_or_visible_stacks(query, ctx)
        resolved = self._resolve_single(
            ctx,
            verb=verb,
            query=query,
            matches=matches,
            item_of=lambda m: m[1],
            not_found_msg="You don't have that.",
        )
        if resolved is None:
            return None

        stack, item = resolved
        if stack.instance_id is None:
            ctx.say(f"You can't {verb} that.", MessageType.WARNING)
            return None

        instance = ctx.session.get(ItemInstance, stack.instance_id)
        if instance is None or get_component_state(instance, "lit") is None:
            ctx.say(f"You can't {verb} that.", MessageType.WARNING)
            return None

        return item, instance

    def light_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Light what?", MessageType.WARNING)
            return

        resolved = self._resolve_lit_source(name_or_id, ctx, verb="light")
        if resolved is None:
            return
        item, instance = resolved

        state = get_component_state(instance, "lit")
        if isinstance(state, dict) and state.get("lit"):
            ctx.say(f"The {item.name} is already lit.", MessageType.WARNING)
            return

        set_component_state(ctx.session, instance, "lit", {"lit": True})
        ctx.say(f"You light the {item.name}.")
        ctx.tell_room(f"{ctx.player.username} lights the {item.name}.")

    def extinguish_item(self, name_or_id: str | None, ctx: GameContext) -> None:
        if name_or_id is None:
            ctx.say("Extinguish what?", MessageType.WARNING)
            return

        resolved = self._resolve_lit_source(name_or_id, ctx, verb="extinguish")
        if resolved is None:
            return
        item, instance = resolved

        state = get_component_state(instance, "lit")
        if isinstance(state, dict) and not state.get("lit"):
            ctx.say(f"The {item.name} isn't lit.", MessageType.WARNING)
            return

        set_component_state(ctx.session, instance, "lit", {"lit": False})
        ctx.say(f"You extinguish the {item.name}.")
        ctx.tell_room(f"{ctx.player.username} extinguishes the {item.name}.")

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
        _record_item_discovery(ctx, item_id)
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


def _record_item_discovery(ctx: GameContext, item_id: str) -> None:
    """Record the first time a player takes or examines an item *definition*
    (Sprint 46), mirroring `met_npcs`. Reassign (not append) so SQLModel flags
    the JSON column dirty; a repeat find is a no-op."""
    if item_id in ctx.player.discovered_items:
        return
    ctx.player.discovered_items = [*ctx.player.discovered_items, item_id]


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
    ctx.say(f"Which do you mean? {options}", MessageType.WARNING)
    ctx.push_update(
        "disambig_pending",
        {"verb": verb, "noun": noun, "choices": [item.name for item in items]},
    )
