"""Sense: the `sense`/`perceive` active ability (Sprint 74.6, flavor A).

An enhanced `search`: rolls a `perception` check and, on success, sweeps the room
for things easily missed — hidden passages (revealed the same way `search` does),
plus a readout of who and what is present. Gated on `ability.keen_senses`, so the
verb is hidden until the skill-tree node is trained.

Concealment note: the engine has no dedicated "hidden item"/"concealed NPC"
field, so `sense` reveals the one real concealment mechanism (hidden exits) and
otherwise reports present NPCs and items as a perception sweep — no invented
schema, and the skill check is genuine.
"""

from __future__ import annotations

from lorecraft.engine.game.checks import skill_check
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.modifiers import get_registry as get_modifier_registry
from lorecraft.features.exploration.rules import (
    is_exit_discovered,
    mark_exit_discovered,
)
from lorecraft.features.inventory.service import format_room_items_summary
from lorecraft.features.skills.service import SkillService

# Easier than a blind `search` (difficulty 10) — a trained sense is meant to
# pick up more, not less.
SENSE_DIFFICULTY = 5

_PERCEPTION_SKILL = "perception"


class SenseService:
    """Handles the `sense` verb: a perception sweep of the current room."""

    def __init__(self, skills: SkillService | None = None) -> None:
        self._skills = skills or SkillService()

    def sense(self, ctx: GameContext) -> None:
        base = self._skills.get_level(ctx.session, ctx.player.id, _PERCEPTION_SKILL)
        modifiers = get_modifier_registry().collect(
            ctx.session, "player", ctx.player.id
        )
        result = skill_check(
            ctx.rng,
            base=base,
            difficulty=SENSE_DIFFICULTY,
            modifiers=modifiers,
            key=f"skill.{_PERCEPTION_SKILL}",
        )

        # Materialize the PlayerStats row (get-or-create) before record_use,
        # which hard-raises on a missing row.
        ctx.player_repo.stats(ctx.player.id)
        self._skills.record_use(ctx.session, ctx.rng, ctx.player.id, _PERCEPTION_SKILL)

        if not result.success:
            ctx.say("You focus your senses but notice nothing unusual.")
            return

        revealed_something = False

        # Hidden passages — the one real concealment mechanism, revealed as `search` does.
        for exit_ in ctx.room_repo.exits(ctx.room.id):
            if exit_.hidden and not is_exit_discovered(
                ctx, ctx.room.id, exit_.direction
            ):
                mark_exit_discovered(ctx, ctx.room.id, exit_.direction)
                ctx.say(
                    f"Your senses pick out a hidden passage to the {exit_.direction}!",
                    MessageType.HINT,
                )
                revealed_something = True

        # Concealed presences — who is here.
        npcs = list(ctx.npc_repo.in_room(ctx.room.id))
        for npc in npcs:
            ctx.say(f"You sense {npc.name} nearby.", MessageType.HINT)
            revealed_something = True

        # And what is here.
        room_items = ctx.item_repo.items_in_room(ctx.room.id)
        if room_items:
            summary = format_room_items_summary(room_items)
            ctx.say(f"Your senses register: {summary}.", MessageType.HINT)
            revealed_something = True

        if not revealed_something:
            ctx.say("You sense nothing here you hadn't already noticed.")
