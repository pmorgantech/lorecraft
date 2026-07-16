"""Movement service."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from lorecraft.features.terrain import definitions as terrain_module
from lorecraft.engine.game.checks import skill_check
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.grammar import OPPOSITE_DIRECTIONS
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.modifiers import get_registry as get_modifier_registry
from lorecraft.engine.game.modifiers import resolve_for
from lorecraft.engine.game.parser import DIRECTION_ALIASES
from lorecraft.engine.models.world import Exit
from lorecraft.features.exploration.rules import is_exit_discovered
from lorecraft.features.disciplines.service import ProficiencyService

if TYPE_CHECKING:
    from lorecraft.features.fatigue.service import FatigueService

_proficiency = ProficiencyService()

# Lock-picking draws its base from the Subterfuge rank; the resolver key stays
# `skill.lockpicking` (Option A).
_LOCKPICK_DISCIPLINE = "subterfuge"

# Picking a lock is meant to be harder than routine skill use — locked doors are
# a deliberate obstacle, so a trained picker still isn't guaranteed.
PICK_DIFFICULTY = 25
DIRECTION_SHORT_NAMES = {
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
    "northeast": "ne",
    "northwest": "nw",
    "southeast": "se",
    "southwest": "sw",
    "up": "u",
    "down": "d",
}


def _carries(ctx: GameContext, item_id: str) -> bool:
    return ctx.stack_repo.quantity_of(Location("player", ctx.player.id), item_id) > 0


def visible_exits_from(ctx: GameContext, room_id: str) -> list[Exit]:
    return [
        exit_
        for exit_ in ctx.room_repo.exits(room_id)
        if not exit_.hidden or is_exit_discovered(ctx, room_id, exit_.direction)
    ]


def visible_exits(ctx: GameContext) -> list[Exit]:
    return visible_exits_from(ctx, ctx.room.id)


class MovementService:
    def __init__(self, fatigue: "FatigueService | None" = None) -> None:
        self.fatigue = fatigue

    def unlock(self, direction: str | None, ctx: GameContext) -> None:
        self._set_locked(direction, ctx, locked=False, verb="unlock")

    def lock(self, direction: str | None, ctx: GameContext) -> None:
        self._set_locked(direction, ctx, locked=True, verb="lock")

    def where(self, destination_ref: str | None, ctx: GameContext) -> None:
        if destination_ref is None or not destination_ref.strip():
            ctx.say("Where are you trying to go?", MessageType.WARNING)
            return

        destination = ctx.room_repo.resolve_ref(destination_ref)
        if destination is None:
            ctx.say("I can't find a unique room by that name.", MessageType.WARNING)
            return
        if destination.id == ctx.room.id:
            ctx.say(f"You are already at {destination.name}.")
            return

        path = self.path_to_room(ctx, destination.id)
        if path is None:
            ctx.say(
                f"I can't find a known path to {destination.name} from here.",
                MessageType.WARNING,
            )
            return

        short_path = ", ".join(DIRECTION_SHORT_NAMES.get(step, step) for step in path)
        ctx.say(f"Path to {destination.name}: {short_path}")

    def exits(self, ctx: GameContext) -> None:
        exits = sorted(exit_.direction for exit_ in visible_exits(ctx))
        if exits:
            ctx.say(f"Visible exits: {', '.join(exits)}.")
            return
        ctx.say("There are no obvious exits.")

    def scan(self, ctx: GameContext) -> None:
        exits = sorted(visible_exits(ctx), key=lambda exit_: exit_.direction)
        if not exits:
            ctx.say("You scan nearby, but there are no obvious exits.")
            return

        ctx.say("Nearby:")
        for exit_ in exits:
            target_room = ctx.room_repo.active(exit_.target_room_id)
            if target_room is None:
                continue
            activity = self._activity_summary(ctx, target_room.id)
            suffix = f" — {activity}" if activity else ""
            ctx.say(f"  {exit_.direction}: {target_room.name}{suffix}.")

    def recall(self, ctx: GameContext) -> None:
        target_room = ctx.room_repo.active(ctx.player.respawn_room_id)
        if target_room is None:
            ctx.say("Your recall point is unavailable.", MessageType.WARNING)
            return
        if target_room.id == ctx.room.id:
            ctx.say(f"You are already at {target_room.name}.")
            return

        previous_room_id = ctx.room.id
        ctx.player.current_room_id = target_room.id
        if target_room.id not in ctx.player.visited_rooms:
            ctx.player.visited_rooms = [*ctx.player.visited_rooms, target_room.id]
        ctx.manager.move_player(ctx.player.id, previous_room_id, target_room.id)
        ctx.room = target_room

        ctx.say(f"You recall to {target_room.name}.")
        ctx.tell_room(f"{ctx.player.username} recalls away.")
        ctx.tell_arrival(f"{ctx.player.username} appears in a shimmer of recall magic.")
        ctx.push_update("room_id", target_room.id)
        ctx.queue_event(
            GameEvent.PLAYER_MOVED,
            player_id=ctx.player.id,
            from_room_id=previous_room_id,
            to_room_id=target_room.id,
            direction="recall",
        )

    def _activity_summary(self, ctx: GameContext, room_id: str) -> str:
        names: list[str] = []
        connected_ids = set(ctx.manager.connected_player_ids())
        for player in ctx.player_repo.in_room(room_id):
            if player.id != ctx.player.id and player.id in connected_ids:
                names.append(player.username)
        names.extend(npc.name for npc in ctx.npc_repo.in_room(room_id))
        return ", ".join(sorted(names))

    def path_to_room(
        self, ctx: GameContext, destination_room_id: str
    ) -> list[str] | None:
        if destination_room_id == ctx.room.id:
            return []

        visited = {ctx.room.id}
        queue: deque[tuple[str, list[str]]] = deque([(ctx.room.id, [])])
        while queue:
            room_id, path = queue.popleft()
            exits = sorted(visible_exits_from(ctx, room_id), key=lambda e: e.direction)
            for exit_ in exits:
                if exit_.target_room_id in visited:
                    continue
                if not self._exit_available_for_path(exit_, ctx):
                    continue
                next_path = [*path, exit_.direction]
                if exit_.target_room_id == destination_room_id:
                    return next_path
                visited.add(exit_.target_room_id)
                queue.append((exit_.target_room_id, next_path))
        return None

    def _exit_available_for_path(self, exit_: Exit, ctx: GameContext) -> bool:
        if exit_.hidden and not is_exit_discovered(ctx, exit_.room_id, exit_.direction):
            return False
        return self._movement_blocked_message(exit_, ctx) is None

    def _movement_blocked_message(self, exit_: Exit, ctx: GameContext) -> str | None:
        if exit_.condition_flags and not all(
            ctx.player.flags.get(flag) for flag in exit_.condition_flags
        ):
            return "Something prevents you from going that way."
        if exit_.locked and (
            exit_.key_item_id is None or not _carries(ctx, exit_.key_item_id)
        ):
            return "The way is locked."
        if ctx.room_repo.active(exit_.target_room_id) is None:
            return "You can't go that way."
        return None

    def _set_locked(
        self, direction: str | None, ctx: GameContext, *, locked: bool, verb: str
    ) -> None:
        if direction is None:
            ctx.say(f"{verb.capitalize()} which way?", MessageType.WARNING)
            return

        normalized = DIRECTION_ALIASES.get(direction.lower(), direction.lower())
        exit_ = ctx.room_repo.exit(ctx.room.id, normalized)
        if exit_ is None:
            ctx.say("There is no exit that way.", MessageType.WARNING)
            return
        if exit_.key_item_id is None:
            ctx.say("That doesn't need a key.", MessageType.WARNING)
            return
        if not _carries(ctx, exit_.key_item_id):
            ctx.say("You don't have the right key.", MessageType.WARNING)
            return
        if exit_.locked == locked:
            state = "locked" if locked else "unlocked"
            ctx.say(f"The way {normalized} is already {state}.", MessageType.WARNING)
            return

        exit_.locked = locked
        state = "locked" if locked else "unlocked"
        ctx.say(f"You {verb} the way {normalized}. It is now {state}.")
        ctx.tell_room(f"{ctx.player.username} {verb}s the way {normalized}.")

    def pick(self, direction: str | None, ctx: GameContext) -> None:
        """Attempt a locked exit *without* its key via a lockpicking check
        (Sprint 74.6). The no-key counterpart to `unlock`; gated on the
        `ability.pick_locks` flag at the command layer, so only trained
        pickers can invoke it. On success the exit is left unlocked, exactly
        as `unlock` leaves it; the roll never fabricates a key."""
        if direction is None:
            ctx.say("Pick which way?", MessageType.WARNING)
            return

        normalized = DIRECTION_ALIASES.get(direction.lower(), direction.lower())
        exit_ = ctx.room_repo.exit(ctx.room.id, normalized)
        if exit_ is None:
            ctx.say("There is no exit that way.", MessageType.WARNING)
            return
        if not exit_.locked:
            ctx.say(f"The way {normalized} isn't locked.", MessageType.WARNING)
            return

        base = _proficiency.get_rank(ctx.session, ctx.player.id, _LOCKPICK_DISCIPLINE)
        result = skill_check(
            ctx.rng,
            base=base,
            difficulty=PICK_DIFFICULTY,
            modifiers=get_modifier_registry().collect(
                ctx.session, "player", ctx.player.id
            ),
            key="skill.lockpicking",
        )
        # Materialize the PlayerStats row (get-or-create) before record_use,
        # which hard-raises on a missing row.
        ctx.player_repo.stats(ctx.player.id)
        _proficiency.record_use(
            ctx.session, ctx.rng, ctx.player.id, _LOCKPICK_DISCIPLINE
        )

        if not result.success:
            ctx.say(f"You work the lock on the way {normalized}, but it holds.")
            return

        exit_.locked = False
        ctx.say(f"You pick the lock. The way {normalized} is now open.")
        ctx.tell_room(f"{ctx.player.username} picks the lock on the way {normalized}.")

    def move(self, direction: str, ctx: GameContext) -> None:
        exit_ = ctx.room_repo.exit(ctx.room.id, direction)
        # Hidden exits are still directly usable — they're just excluded from
        # the room description's exit list (see InventoryService.look()) and
        # `search` (Sprint 25.1) reveals them there. Docs: world_building.md
        # "Hidden Exits" — "the player must try the command directly".
        if exit_ is None:
            ctx.say("You can't go that way.", MessageType.WARNING)
            return
        blocked_message = self._movement_blocked_message(exit_, ctx)
        if blocked_message is not None:
            ctx.say(blocked_message, MessageType.WARNING)
            return

        target_room = ctx.room_repo.active(exit_.target_room_id)
        if target_room is None:
            ctx.say("You can't go that way.", MessageType.WARNING)
            return

        if self.fatigue is not None and not self.fatigue.consume_for_travel(
            ctx, target_room
        ):
            return

        terrain_def = terrain_module.get_registry().get(target_room.terrain)
        if terrain_def is not None and terrain_def.required_discipline is not None:
            discipline = terrain_def.required_discipline
            base = _proficiency.get_rank(ctx.session, ctx.player.id, discipline)
            effective = resolve_for(
                ctx.session,
                "player",
                ctx.player.id,
                # The discipline id doubles as the `skill.<name>` resolver key for
                # the gated terrain checks (survival) — Option A namespace.
                f"skill.{discipline}",
                base=base,
            )
            if effective < terrain_def.required_discipline_min:
                ctx.say(
                    f"You aren't skilled enough to venture into the "
                    f"{target_room.terrain} safely.",
                    MessageType.WARNING,
                )
                return
            # Materialize the PlayerStats row (get-or-create) before record_use,
            # which hard-raises on a missing row.
            ctx.player_repo.stats(ctx.player.id)
            _proficiency.record_use(ctx.session, ctx.rng, ctx.player.id, discipline)

        previous_room_id = ctx.room.id
        ctx.player.current_room_id = target_room.id
        if target_room.id not in ctx.player.visited_rooms:
            ctx.player.visited_rooms = [*ctx.player.visited_rooms, target_room.id]
        ctx.manager.move_player(ctx.player.id, previous_room_id, target_room.id)
        ctx.room = target_room

        ctx.say(f"You go {direction}.")
        ctx.tell_room(f"{ctx.player.username} leaves {direction}.")
        arrival_from = OPPOSITE_DIRECTIONS.get(direction)
        arrival_text = (
            f"{ctx.player.username} arrives from the {arrival_from}."
            if arrival_from
            else f"{ctx.player.username} arrives."
        )
        ctx.tell_arrival(arrival_text)
        ctx.push_update("room_id", target_room.id)
        ctx.queue_event(
            GameEvent.PLAYER_MOVED,
            player_id=ctx.player.id,
            from_room_id=previous_room_id,
            to_room_id=target_room.id,
            direction=direction,
        )
