"""Read-only character info queries: traits, skills, reputation (Sprint 24)."""

from __future__ import annotations

from lorecraft.game import skills as skills_module
from lorecraft.engine.game import traits as traits_module
from lorecraft.engine.game.context import GameContext
from lorecraft.features.reputation.repo import ReputationRepo


class CharacterInfoService:
    def list_traits(self, ctx: GameContext) -> None:
        registry = traits_module.get_registry()
        names = sorted(registry.traits_for(ctx.session, "player", ctx.player.id))
        if not names:
            ctx.say("You have no notable traits.")
            ctx.push_update("traits", [])
            return

        ctx.say("Your traits:")
        entries = []
        for name in names:
            trait_def = registry.get(name)
            description = trait_def.description if trait_def is not None else ""
            ctx.say(f"  {name}: {description}")
            entries.append({"name": name, "description": description})
        ctx.push_update("traits", entries)

    def list_skills(self, ctx: GameContext) -> None:
        stats = ctx.player_repo.stats(ctx.player.id)
        skill_levels = stats.skills if stats is not None else {}
        registry = skills_module.get_registry()

        ctx.say("Your skills:")
        entries = []
        for skill_def in sorted(registry.all_skills(), key=lambda s: s.name):
            level = skill_levels.get(skill_def.name, 0)
            ctx.say(f"  {skill_def.name}: {level}")
            entries.append({"name": skill_def.name, "level": level})
        ctx.push_update("skills", entries)

    def list_reputation(self, ctx: GameContext) -> None:
        repo = ReputationRepo(ctx.session)
        rows = repo.for_player(ctx.player.id)
        if not rows:
            ctx.say("You have no reputation with anyone yet.")
            ctx.push_update("reputation", [])
            return

        ctx.say("Your reputation:")
        entries = []
        for row in rows:
            ctx.say(f"  {row.target_type} {row.target_id}: {row.standing}")
            entries.append(
                {
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                    "standing": row.standing,
                }
            )
        ctx.push_update("reputation", entries)
