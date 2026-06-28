"""Movement service."""

from __future__ import annotations

from lorecraft.game.context import GameContext
from lorecraft.game.events import GameEvent


class MovementService:
    def move(self, direction: str, ctx: GameContext) -> None:
        exit_ = ctx.room_repo.exit(ctx.room.id, direction)
        if exit_ is None or exit_.hidden:
            ctx.say("You can't go that way.")
            return
        if exit_.locked and (
            exit_.key_item_id is None or exit_.key_item_id not in ctx.player.inventory
        ):
            ctx.say("The way is locked.")
            return

        target_room = ctx.room_repo.active(exit_.target_room_id)
        if target_room is None:
            ctx.say("You can't go that way.")
            return

        previous_room_id = ctx.room.id
        ctx.player.current_room_id = target_room.id
        if target_room.id not in ctx.player.visited_rooms:
            ctx.player.visited_rooms = [*ctx.player.visited_rooms, target_room.id]
        ctx.manager.move_player(ctx.player.id, previous_room_id, target_room.id)
        ctx.room = target_room

        ctx.say(f"You go {direction}.")
        ctx.tell_room(f"{ctx.player.username} leaves {direction}.")
        ctx.push_update("room_id", target_room.id)
        ctx.queue_event(
            GameEvent.PLAYER_MOVED,
            player_id=ctx.player.id,
            from_room_id=previous_room_id,
            to_room_id=target_room.id,
            direction=direction,
        )
