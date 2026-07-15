"""WebSocket fanout for combat domain events."""

from __future__ import annotations

import asyncio
import logging

from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.message_types import MessageType
from lorecraft.types import JsonObject

log = logging.getLogger(__name__)


def register_combat_broadcasts(bus: EventBus, manager: ConnectionManager) -> None:
    """Broadcast combat resolution prose and structured state to room clients."""

    def _handle(event: Event, ctx: object) -> None:
        del ctx
        try:
            asyncio.create_task(broadcast_combat_resolution(manager, event))
        except RuntimeError:
            # No running event loop in some unit/headless contexts; the domain
            # event has already been emitted, so only live browser fanout is skipped.
            log.debug("combat_broadcast_skipped_no_event_loop")

    bus.on(GameEvent.PLAYER_ATTACKED, _handle)
    bus.on(GameEvent.NPC_ATTACKED, _handle)


async def broadcast_combat_resolution(manager: ConnectionManager, event: Event) -> None:
    payload = event.payload
    room_id = payload.get("room_id")
    if not isinstance(room_id, str) or not room_id:
        return

    sequence = payload.get("sequence", 0)
    prose = payload.get("prose")
    if isinstance(prose, str) and prose:
        await manager.broadcast_to_room(
            room_id,
            {
                "type": "feed_append",
                "content": prose,
                "message_type": MessageType.COMBAT.value,
                "sequence": sequence,
            },
        )

    combat_update = payload.get("combat_update")
    if isinstance(combat_update, dict):
        update_payload: JsonObject = {
            "type": "combat_update",
            **combat_update,
        }
        await manager.broadcast_to_room(room_id, update_payload)
