"""Room-authored treasure rolls for exploration."""

from __future__ import annotations

import logging

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.models.world import Room
from lorecraft.types import JsonObject

log = logging.getLogger(__name__)


class RoomLootService:
    """Rolls a room ``loot_table`` once per player-room visit.

    The room owns the policy in YAML; Tier 1 only supplies the item-location
    primitive that materializes the chosen reward.
    """

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.PLAYER_MOVED, self._on_player_moved)

    def _on_player_moved(self, event: Event, ctx: object) -> None:
        if not isinstance(ctx, GameContext):
            return
        room_id = event.payload.get("to_room_id")
        if not isinstance(room_id, str):
            return
        room = ctx.session.get(Room, room_id)
        if room is None or not room.loot_table:
            return

        flag_key = f"room_loot_checked:{room_id}"
        if ctx.player.flags.get(flag_key) is True:
            return

        ctx.player.flags = {**ctx.player.flags, flag_key: True}
        table = room.loot_table
        chance = _as_float(table.get("chance"), 1.0)
        if not ctx.rng.chance(max(0.0, min(1.0, chance))):
            return

        entry = _choose_entry(ctx, table)
        if entry is None:
            return
        item_id = entry.get("item_id")
        if not isinstance(item_id, str) or not item_id:
            return
        quantity = _roll_quantity(ctx, entry.get("quantity"))
        try:
            ctx.item_location.spawn(item_id, Location("room", room_id), quantity)
        except Exception:
            log.exception("room_loot_spawn_failed room=%s item=%s", room_id, item_id)
            return
        message = entry.get("message", table.get("message"))
        if isinstance(message, str) and message:
            ctx.say(message, MessageType.HINT)


def _choose_entry(ctx: GameContext, table: JsonObject) -> JsonObject | None:
    raw_entries = table.get("entries")
    if not isinstance(raw_entries, list):
        return None
    entries = [entry for entry in raw_entries if isinstance(entry, dict)]
    if not entries:
        return None
    total = sum(max(0, _as_int(entry.get("weight"), 1)) for entry in entries)
    if total <= 0:
        return None
    roll = ctx.rng.randint(1, total)
    cursor = 0
    for entry in entries:
        cursor += max(0, _as_int(entry.get("weight"), 1))
        if roll <= cursor:
            return entry
    return None


def _roll_quantity(ctx: GameContext, value: object) -> int:
    if isinstance(value, dict):
        minimum = _as_int(value.get("min"), 1)
        maximum = _as_int(value.get("max"), minimum)
        return max(1, ctx.rng.randint(min(minimum, maximum), max(minimum, maximum)))
    return max(1, _as_int(value, 1))


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _as_float(value: object, default: float) -> float:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else default
    )
