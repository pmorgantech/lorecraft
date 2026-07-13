"""Search command + discovery rewards (Sprint 25.1)."""

from __future__ import annotations

from lorecraft.engine.game.checks import skill_check
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.features.exploration.rules import (
    is_exit_discovered,
    mark_exit_discovered,
)
from lorecraft.engine.game.modifiers import get_registry as get_modifier_registry
from lorecraft.features.progression.feedback import narrate_level_up
from lorecraft.features.progression.rewards import apply_rewards
from lorecraft.features.skills.service import SkillService

# A routine search; a room author could later vary this per-room via terrain
# or a room flag, but a flat difficulty keeps the first cut simple.
SEARCH_DIFFICULTY = 10
DISCOVERY_XP = 5


class ExplorationService:
    def __init__(self, skills: SkillService | None = None) -> None:
        self.skills = skills or SkillService()

    def search(self, ctx: GameContext) -> None:
        base = self.skills.get_level(ctx.session, ctx.player.id, "perception")
        modifiers = get_modifier_registry().collect(
            ctx.session, "player", ctx.player.id
        )
        result = skill_check(
            ctx.rng,
            base=base,
            difficulty=SEARCH_DIFFICULTY,
            modifiers=modifiers,
            key="skill.perception",
        )

        # Materialize the PlayerStats row (get-or-create) before record_use,
        # which hard-raises on a missing row.
        ctx.player_repo.stats(ctx.player.id)
        self.skills.record_use(ctx.session, ctx.rng, ctx.player.id, "perception")

        if not result.success:
            ctx.say("You search the area but find nothing new.")
            return

        hidden_exits = [
            exit_
            for exit_ in ctx.room_repo.exits(ctx.room.id)
            if exit_.hidden
            and not is_exit_discovered(ctx, ctx.room.id, exit_.direction)
        ]
        if not hidden_exits:
            ctx.say("You search the area but find nothing new.")
            return

        for exit_ in hidden_exits:
            mark_exit_discovered(ctx, ctx.room.id, exit_.direction)
            ctx.say(
                f"You discover a hidden passage to the {exit_.direction}!",
                MessageType.HINT,
            )

        # Route the discovery reward through the Tier 2 interpreter so a
        # threshold-crossing discovery also fires the config-driven level-up
        # payout — no duplicated leveling math here. DISCOVERY_XP stays
        # exploration's own policy value; the interpreter owns the curve.
        # The returned outcome must be narrated (Sprint 73.9): otherwise a
        # discovery that crosses a level silently grants the payout but says
        # nothing. Reuse the same feedback path the quest turn-in uses.
        outcome = apply_rewards(ctx, {"xp": DISCOVERY_XP})
        narrate_level_up(ctx, outcome)
