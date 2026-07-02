"""Movement service."""

from __future__ import annotations

from lorecraft.game.context import GameContext
from lorecraft.game.events import GameEvent
from lorecraft.game.parser import DIRECTION_ALIASES


class MovementService:
    def unlock(self, direction: str | None, ctx: GameContext) -> None:
        self._set_locked(direction, ctx, locked=False, verb="unlock")

    def lock(self, direction: str | None, ctx: GameContext) -> None:
        self._set_locked(direction, ctx, locked=True, verb="lock")

    def _set_locked(
        self, direction: str | None, ctx: GameContext, *, locked: bool, verb: str
    ) -> None:
        if direction is None:
            ctx.say(f"{verb.capitalize()} which way?")
            return

        normalized = DIRECTION_ALIASES.get(direction.lower(), direction.lower())
        exit_ = ctx.room_repo.exit(ctx.room.id, normalized)
        if exit_ is None:
            ctx.say("There is no exit that way.")
            return
        if exit_.key_item_id is None:
            ctx.say("That doesn't need a key.")
            return
        if exit_.key_item_id not in ctx.player.inventory:
            ctx.say("You don't have the right key.")
            return
        if exit_.locked == locked:
            state = "locked" if locked else "unlocked"
            ctx.say(f"The way {normalized} is already {state}.")
            return

        exit_.locked = locked
        state = "locked" if locked else "unlocked"
        ctx.say(f"You {verb} the way {normalized}. It is now {state}.")
        ctx.tell_room(f"{ctx.player.username} {verb}s the way {normalized}.")

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
