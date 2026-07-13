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

from lorecraft.engine.game.channels import Channel, ChatScope
from lorecraft.engine.game.channels import get_registry as get_channel_registry
from lorecraft.engine.game.connection_manager import ConnectionManagerProtocol
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.models.player import Player
from lorecraft.types import JsonObject, JsonValue

log = logging.getLogger(__name__)

_AFFECTED_PANELS: list[JsonValue] = [
    "room-description",
    "inventory",
    "minimap",
    "players-online",
]


def _subscribed(ctx: GameContext, player_id: str, channel: Channel | None) -> bool:
    """Whether a P2ALL recipient should get this channel's chat (Sprint 52.5).

    Non-muteable (or unregistered) channels always deliver. For muteable topic
    channels, the player's raw `preferences["channel_subscriptions"]` blob is
    consulted (the engine reads the model field directly — resolving the full
    preferences object is a webui concern); absent means the channel's
    `default_subscribed`.
    """
    if channel is None or not channel.muteable:
        return True
    player = ctx.session.get(Player, player_id)
    if player is None:
        return channel.default_subscribed
    subscriptions = player.preferences.get("channel_subscriptions")
    if not isinstance(subscriptions, dict):
        return channel.default_subscribed
    value = subscriptions.get(channel.id)
    if isinstance(value, bool):
        return value
    return channel.default_subscribed


async def broadcast_command_effects(
    manager: ConnectionManagerProtocol, ctx: GameContext, *, pre_room_id: str
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
                    "message_type": MessageType.ROOM_EVENT.value,
                },
                exclude=actor_id,
            )
        except Exception as exc:
            log.debug("room_feed_broadcast_failed: %s", exc)

    # Chat (Sprint 45 split, Sprint 52 channels): same feed_append shape but
    # tagged "chat" + the channel id, routed by each entry's delivery scope —
    # P2ROOM to the actor's room, P2ALL to every connected player subscribed
    # to the channel, P2P to exactly one target. Chat never moves the player,
    # so the narration room is the actor's current room in practice.
    channel_registry = get_channel_registry()
    for chat in ctx.chat_outbox:
        payload: JsonObject = {
            "type": "feed_append",
            "content": chat.text,
            "message_type": MessageType.CHAT.value,
            "channel": chat.channel,
        }
        try:
            if chat.scope is ChatScope.P2P:
                if chat.target_player_id:
                    await manager.send_to_player(chat.target_player_id, payload)
            elif chat.scope is ChatScope.P2ALL:
                channel = channel_registry.get(chat.channel)
                for player_id in manager.connected_player_ids():
                    if player_id == actor_id:
                        continue
                    if not _subscribed(ctx, player_id, channel):
                        continue
                    await manager.send_to_player(player_id, payload)
            else:  # P2ROOM
                if narration_room:
                    await manager.broadcast_to_room(
                        narration_room, payload, exclude=actor_id
                    )
        except Exception as exc:
            log.debug("chat_feed_broadcast_failed: %s", exc)

    for arrival_msg in ctx.arrival_messages:
        if not after_room_id:
            continue
        try:
            await manager.broadcast_to_room(
                after_room_id,
                {
                    "type": "feed_append",
                    "content": str(arrival_msg),
                    "message_type": MessageType.ROOM_EVENT.value,
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

    # Deferred deliveries (Sprint 47): WS pushes a synchronous handler queued for
    # another player (e.g. moving a follower). Exception-isolated like the room
    # broadcasts above — one failed push must not drop the rest.
    for deliver in ctx.pending_deliveries:
        try:
            await deliver()
        except Exception as exc:
            log.debug("pending_delivery_failed: %s", exc)
    ctx.pending_deliveries.clear()
