"""Pure `look` policy (Tier 2) expressed against the protocol contract.

`look_effects` is a pure function: no `GameContext`, no session, no repo access. It
consumes a fully-materialized `ScriptRequest` and returns a `ScriptResult` whose
messages reproduce, in order, exactly what `InventoryService.look` emits today via
`ctx.say(...)` / `ctx.push_update("room_id", ...)`. `look` is fully read-only, so it
proposes zero effects, events, or scheduled work.

Formatting-work split: the repo/session-dependent reads (filtering exits by
visibility, terrain-registry lookup, enumerating room item stacks) stay in the
`InventoryService.look` shim, which lands their *results* in the request snapshot.
Everything that is pure — message ordering, exit sorting, item-label formatting,
and the conditional "no exits" / "you see" lines — lives here, so this function
carries `look`'s actual output opinion.
"""

from __future__ import annotations

from lorecraft.engine.game.message_types import MessageType
from lorecraft.protocol import (
    EntitySnapshot,
    Feed,
    OutboundMessage,
    PanelUpdate,
    ScriptRequest,
    ScriptResult,
)

_SYSTEM = MessageType.SYSTEM.value

# room_snapshot.attributes keys this policy reads.
ATTR_NAME = "name"
ATTR_DESCRIPTION = "description"
ATTR_TERRAIN_SUFFIX = "terrain_suffix"
ATTR_EXITS = "exits"

# selected_related_entities item-snapshot attribute keys.
ITEM_ATTR_NAME = "name"
ITEM_ATTR_QUANTITY = "quantity"


def _entry_label(name: str, quantity: int) -> str:
    """Reproduce `inventory.service.format_inventory_entry` without a back-import."""
    if quantity > 1:
        return f"[{quantity}] {name}"
    return name


def _room_items_summary(items: list[EntitySnapshot]) -> str:
    """Reproduce `format_room_items_summary`: grouped labels, sorted, comma-joined."""
    labels = [
        _entry_label(
            str(item.attributes.get(ITEM_ATTR_NAME, "")),
            _quantity_of(item),
        )
        for item in items
    ]
    return ", ".join(sorted(labels))


def _quantity_of(item: EntitySnapshot) -> int:
    """Read an item snapshot's quantity attribute, defaulting to 1."""
    raw = item.attributes.get(ITEM_ATTR_QUANTITY, 1)
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else 1


def look_effects(request: ScriptRequest) -> ScriptResult:
    """Build the ordered `look` output from a materialized room snapshot."""
    room = request.room_snapshot
    attrs = room.attributes
    messages: list[OutboundMessage] = []

    messages.append(Feed(text=str(attrs.get(ATTR_NAME, "")), message_type=_SYSTEM))
    messages.append(
        Feed(text=str(attrs.get(ATTR_DESCRIPTION, "")), message_type=_SYSTEM)
    )

    terrain_suffix = attrs.get(ATTR_TERRAIN_SUFFIX)
    if isinstance(terrain_suffix, str) and terrain_suffix:
        messages.append(Feed(text=terrain_suffix, message_type=_SYSTEM))

    raw_exits = attrs.get(ATTR_EXITS)
    visible_exits = [str(d) for d in raw_exits] if isinstance(raw_exits, list) else []
    if visible_exits:
        messages.append(
            Feed(
                text=f"Exits: {', '.join(sorted(visible_exits))}.",
                message_type=_SYSTEM,
            )
        )
    else:
        messages.append(Feed(text="There are no obvious exits.", message_type=_SYSTEM))

    room_items = [
        entity for entity in request.selected_related_entities if entity.kind == "item"
    ]
    if room_items:
        summary = _room_items_summary(room_items)
        messages.append(Feed(text=f"You see: {summary}.", message_type=_SYSTEM))

    messages.append(PanelUpdate(key="room_id", value=room.id))

    return ScriptResult(messages=messages)
