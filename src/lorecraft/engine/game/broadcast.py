"""Post-command room broadcast — the shared step 12 of the command lifecycle.

architecture.md §26 defines a 13-step transaction/event/audit lifecycle every
command follows; step 12 ("broadcast WebSocket messages to room") used to be
implemented twice and had drifted: `web/frontend.py`'s `POST /command` path
broadcast a player's `ctx.room_messages` narration and a `state_change` nudge
to other WS-connected room occupants, but `main.py`'s raw `/ws` command loop
never did (Sprint 12's simulation tests surfaced this gap). Both entry points
now call `broadcast_command_effects()` after `CommandEngine.handle_command()`
returns, so they can't diverge again.
"""

from __future__ import annotations

import logging

from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.types import JsonValue

log = logging.getLogger(__name__)

_AFFECTED_PANELS: list[JsonValue] = [
    "room-description",
    "inventory",
    "minimap",
    "players-online",
]


async def broadcast_command_effects(
    manager: ConnectionManager, ctx: GameContext, *, pre_room_id: str
) -> None:
    """Broadcast one command's room-visible effects to other players.

    `pre_room_id` is the actor's room before the command ran. If the command
    moved them, `ctx.room_messages` narration (e.g. "X leaves north.") goes
    to the room they left, since that's where it's narratively visible;
    `ctx.arrival_messages` narration (e.g. "X arrives from the south.") goes
    to the room they're now in, so occupants there see the arrival in their
    feed, not just a silent panel refresh. The `state_change` nudge goes to
    the room they're in now (so clients there refresh room/inventory/players
    panels), and — if the room changed — a second `state_change` goes to the
    room they left too, so remaining occupants there also refresh their
    `players-online` panel.
    """
    actor_id = ctx.player.id
    after_room_id = ctx.player.current_room_id
    room_changed = after_room_id != pre_room_id
    narration_room = pre_room_id if room_changed and pre_room_id else after_room_id

    for room_msg in ctx.room_messages:
        if not narration_room:
            continue
        try:
            await manager.broadcast_to_room(
                narration_room,
                {
                    "type": "feed_append",
                    "content": str(room_msg),
                    "message_type": "room_event",
                },
                exclude=actor_id,
            )
        except Exception as exc:
            log.debug("room_feed_broadcast_failed: %s", exc)

    for arrival_msg in ctx.arrival_messages:
        if not after_room_id:
            continue
        try:
            await manager.broadcast_to_room(
                after_room_id,
                {
                    "type": "feed_append",
                    "content": str(arrival_msg),
                    "message_type": "room_event",
                },
                exclude=actor_id,
            )
        except Exception as exc:
            log.debug("arrival_feed_broadcast_failed: %s", exc)

    if after_room_id:
        try:
            await manager.broadcast_to_room(
                after_room_id,
                {
                    "type": "state_change",
                    "affected_panels": _AFFECTED_PANELS,
                    "actor_id": actor_id,
                },
                exclude=actor_id,
            )
        except Exception as exc:
            log.debug("state_change_broadcast_failed: %s", exc)

    if room_changed and pre_room_id:
        try:
            await manager.broadcast_to_room(
                pre_room_id,
                {
                    "type": "state_change",
                    "affected_panels": _AFFECTED_PANELS,
                    "actor_id": actor_id,
                },
            )
        except Exception as exc:
            log.debug("state_change_broadcast_left_room_failed: %s", exc)
