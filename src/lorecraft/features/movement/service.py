"""Movement service."""

from __future__ import annotations

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
from lorecraft.features.skills.service import SkillService

_skills = SkillService()

# Picking a lock is meant to be harder than routine skill use — locked doors are
# a deliberate obstacle, so a trained picker still isn't guaranteed.
PICK_DIFFICULTY = 25


def _carries(ctx: GameContext, item_id: str) -> bool:
    return ctx.stack_repo.quantity_of(Location("player", ctx.player.id), item_id) > 0


class MovementService:
    def unlock(self, direction: str | None, ctx: GameContext) -> None:
        self._set_locked(direction, ctx, locked=False, verb="unlock")

    def lock(self, direction: str | None, ctx: GameContext) -> None:
        self._set_locked(direction, ctx, locked=True, verb="lock")

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

        base = _skills.get_level(ctx.session, ctx.player.id, "lockpicking")
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
        _skills.record_use(ctx.session, ctx.rng, ctx.player.id, "lockpicking")

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
        if exit_.condition_flags and not all(
            ctx.player.flags.get(flag) for flag in exit_.condition_flags
        ):
            ctx.say("Something prevents you from going that way.", MessageType.WARNING)
            return
        if exit_.locked and (
            exit_.key_item_id is None or not _carries(ctx, exit_.key_item_id)
        ):
            ctx.say("The way is locked.", MessageType.WARNING)
            return

        target_room = ctx.room_repo.active(exit_.target_room_id)
        if target_room is None:
            ctx.say("You can't go that way.", MessageType.WARNING)
            return

        terrain_def = terrain_module.get_registry().get(target_room.terrain)
        if terrain_def is not None and terrain_def.required_skill is not None:
            base = _skills.get_level(
                ctx.session, ctx.player.id, terrain_def.required_skill
            )
            effective = resolve_for(
                ctx.session,
                "player",
                ctx.player.id,
                f"skill.{terrain_def.required_skill}",
                base=base,
            )
            if effective < terrain_def.required_skill_min:
                ctx.say(
                    f"You aren't skilled enough to venture into the "
                    f"{target_room.terrain} safely.",
                    MessageType.WARNING,
                )
                return
            # Materialize the PlayerStats row (get-or-create) before record_use,
            # which hard-raises on a missing row.
            ctx.player_repo.stats(ctx.player.id)
            _skills.record_use(
                ctx.session, ctx.rng, ctx.player.id, terrain_def.required_skill
            )

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
