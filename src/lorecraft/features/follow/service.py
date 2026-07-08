"""Follow service: the in-memory follow graph and the movement cascade.

Follow state is transient social state, held in memory (follower_id -> target_id)
rather than persisted — a disconnect simply stops the follow. On every
`PLAYER_MOVED`, co-located connected followers are auto-moved in the same
direction through the *standard* `MovementService.move` gates; a follower who
fails a gate (locked/terrain/flag) has their follow broken with a message to
both sides. Chains (A->B->C) cascade naturally because each auto-move emits its
own `PLAYER_MOVED`; cycles are rejected when the follow is created.
"""

from __future__ import annotations

import dataclasses

from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.features.movement.service import MovementService
from lorecraft.types import JsonObject, JsonValue

_FOLLOW_PANELS: list[JsonValue] = [
    "room-description",
    "inventory",
    "minimap",
    "players-online",
]


class FollowService:
    def __init__(self, movement: MovementService | None = None) -> None:
        self._movement = movement or MovementService()
        # follower_id -> target_id
        self._following: dict[str, str] = {}

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.PLAYER_MOVED, self._on_player_moved)

    # ---- queries -------------------------------------------------------

    def target_of(self, follower_id: str) -> str | None:
        return self._following.get(follower_id)

    def followers_of(self, target_id: str) -> list[str]:
        return [f for f, t in self._following.items() if t == target_id]

    # ---- commands ------------------------------------------------------

    def follow(self, target_name: str | None, ctx: GameContext) -> None:
        if target_name is None:
            self._show_status(ctx)
            return

        target = ctx.player_repo.by_username(target_name)
        if target is None or target.current_room_id != ctx.room.id:
            ctx.say(f"There's no one here called {target_name}.")
            return
        if target.id == ctx.player.id:
            ctx.say("You can't follow yourself.")
            return
        if self._following.get(ctx.player.id) == target.id:
            ctx.say(f"You are already following {target.username}.")
            return
        if self._would_cycle(follower_id=ctx.player.id, target_id=target.id):
            ctx.say(f"{target.username} is already following you.")
            return

        self._following[ctx.player.id] = target.id
        ctx.say(f"You begin following {target.username}.")
        self._notify(
            ctx, target.id, f"{ctx.player.username} begins following you.", chat=False
        )

    def unfollow(self, ctx: GameContext) -> None:
        target_id = self._following.pop(ctx.player.id, None)
        if target_id is None:
            ctx.say("You aren't following anyone.")
            return
        target = ctx.player_repo.get(target_id)
        name = target.username if target is not None else "them"
        ctx.say(f"You stop following {name}.")
        if target is not None:
            self._notify(
                ctx,
                target.id,
                f"{ctx.player.username} stops following you.",
                chat=False,
            )

    async def break_on_disconnect(
        self, manager: ConnectionManager, player_repo: PlayerRepo, player_id: str
    ) -> None:
        """Terminate any follow involving a player who just disconnected.

        Follow state is transient (see the module docstring): a disconnect stops
        the follow rather than silently resuming it when the player returns.
        Both directions are cleared — the leaver's own follow, and anyone
        following the leaver — and any still-connected player on the other end
        is told, so their follow status and `players-online` panel don't lie.
        Called from the async disconnect handlers (graceful quit + involuntary
        drop) where a `ConnectionManager` is available to push the notice; the
        follow graph itself is process-local so nothing is persisted.
        """
        leaver = player_repo.get(player_id)
        leaver_name = leaver.username if leaver is not None else "someone"

        # The leaver was following someone: stop, and tell that target.
        target_id = self._following.pop(player_id, None)
        if target_id is not None and manager.is_connected(target_id):
            await self._push_disconnect_notice(
                manager, target_id, f"{leaver_name} is no longer following you."
            )

        # Others were following the leaver: orphan them, and tell each one.
        for follower_id in self.followers_of(player_id):
            self._following.pop(follower_id, None)
            if manager.is_connected(follower_id):
                await self._push_disconnect_notice(
                    manager,
                    follower_id,
                    f"You stop following {leaver_name} — they have left.",
                )

    async def _push_disconnect_notice(
        self, manager: ConnectionManager, player_id: str, text: str
    ) -> None:
        await manager.send_to_player(
            player_id,
            {"type": "feed_append", "content": text, "message_type": "room_event"},
        )
        await manager.send_to_player(
            player_id,
            {
                "type": "state_change",
                "affected_panels": ["players-online"],
                "actor_id": player_id,
            },
        )

    def _show_status(self, ctx: GameContext) -> None:
        target_id = self._following.get(ctx.player.id)
        if target_id is not None:
            target = ctx.player_repo.get(target_id)
            name = target.username if target is not None else target_id
            ctx.say(f"You are following {name}.")
        else:
            ctx.say("You aren't following anyone.")
        followers = self.followers_of(ctx.player.id)
        if followers:
            names = sorted(
                (p.username if (p := ctx.player_repo.get(f)) is not None else f)
                for f in followers
            )
            ctx.say(f"Following you: {', '.join(names)}.")

    # ---- movement cascade ---------------------------------------------

    def _on_player_moved(self, event: Event, ctx: object) -> None:
        if not isinstance(ctx, GameContext):
            return
        payload = event.payload
        target_id = str(payload.get("player_id", ""))
        from_room_id = str(payload.get("from_room_id", ""))
        to_room_id = str(payload.get("to_room_id", ""))
        direction = str(payload.get("direction", ""))
        if not (target_id and to_room_id and direction):
            return

        for follower_id in self.followers_of(target_id):
            self._advance_follower(
                ctx,
                follower_id=follower_id,
                from_room_id=from_room_id,
                to_room_id=to_room_id,
                direction=direction,
            )

    def _advance_follower(
        self,
        ctx: GameContext,
        *,
        follower_id: str,
        from_room_id: str,
        to_room_id: str,
        direction: str,
    ) -> None:
        # Only move a follower who is connected and was co-located with the
        # target (a follower who wandered off isn't dragged from afar).
        if not ctx.manager.is_connected(follower_id):
            return
        follower = ctx.player_repo.get(follower_id)
        if follower is None or follower.current_room_id != from_room_id:
            return
        from_room = ctx.room_repo.active(from_room_id)
        if from_room is None:
            return

        sub_ctx = self._follower_context(ctx, follower, from_room)
        self._movement.move(direction, sub_ctx)

        if follower.current_room_id != to_room_id:
            # A gate (locked/terrain/flag) stopped the follower — break the
            # follow and tell both sides.
            self._break_follow(ctx, follower, reason=sub_ctx.messages)
            return

        self._deliver_follow_move(ctx, follower, direction)
        # Cascade: the follower's own move drives *their* followers (A->B->C).
        sub_ctx.flush_events()

    def _follower_context(
        self, ctx: GameContext, follower: Player, from_room: Room
    ) -> GameContext:
        """A sub-context for re-running movement as the follower. Shares the
        session/repos/manager and the root's `pending_deliveries` (so cascaded
        moves' pushes reach the same drain), but gets fresh message/event
        buffers so the follower's narration never leaks into the mover's reply."""
        return dataclasses.replace(
            ctx,
            player=follower,
            room=from_room,
            messages=[],
            room_messages=[],
            arrival_messages=[],
            chat_echoes=[],
            chat_outbox=[],
            updates={},
            pending_events=[],
            parsed_command=None,
            pending_deliveries=ctx.pending_deliveries,
        )

    def _break_follow(
        self, ctx: GameContext, follower: Player, *, reason: list[str]
    ) -> None:
        # The target the follower was following is the mover whose PLAYER_MOVED
        # triggered this cascade — i.e. ctx.player.
        self._following.pop(follower.id, None)
        detail = reason[0] if reason else "You can't follow that way."
        self._notify(
            ctx,
            follower.id,
            f"You lose sight of {ctx.player.username}. {detail}",
            chat=False,
        )
        self._notify(
            ctx,
            ctx.player.id,
            f"{follower.username} can no longer follow you.",
            chat=False,
        )

    def _deliver_follow_move(
        self, ctx: GameContext, follower: Player, direction: str
    ) -> None:
        feed: JsonObject = {
            "type": "feed_append",
            "content": f"You follow {ctx.player.username} {direction}.",
            "message_type": "room_event",
        }
        state: JsonObject = {
            "type": "state_change",
            "affected_panels": _FOLLOW_PANELS,
            "actor_id": follower.id,
        }
        self._defer_push(ctx, follower.id, feed)
        self._defer_push(ctx, follower.id, state)

    # ---- helpers -------------------------------------------------------

    def _would_cycle(self, *, follower_id: str, target_id: str) -> bool:
        """True if `follower_id` following `target_id` would close a cycle —
        i.e. the target already (transitively) follows the follower."""
        seen: set[str] = set()
        cursor: str | None = target_id
        while cursor is not None and cursor not in seen:
            if cursor == follower_id:
                return True
            seen.add(cursor)
            cursor = self._following.get(cursor)
        return False

    def _notify(
        self, ctx: GameContext, player_id: str, text: str, *, chat: bool
    ) -> None:
        """Say to `player_id`: directly if it's the actor, else a deferred push."""
        if player_id == ctx.player.id:
            ctx.say(text)
            return
        self._defer_push(
            ctx,
            player_id,
            {
                "type": "feed_append",
                "content": text,
                "message_type": "chat" if chat else "room_event",
            },
        )

    def _defer_push(
        self, ctx: GameContext, player_id: str, message: JsonObject
    ) -> None:
        manager = ctx.manager

        async def _send() -> None:
            await manager.send_to_player(player_id, message)

        ctx.defer_delivery(_send)
