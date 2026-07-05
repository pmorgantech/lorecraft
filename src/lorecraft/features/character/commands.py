"""Character info commands: traits, skills, reputation (Sprint 24)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.features.character.service import CharacterInfoService


def register_character_commands(
    registry: CommandRegistry, character_info: CharacterInfoService | None = None
) -> None:
    service = character_info or CharacterInfoService()

    @registry.register(
        "traits",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="traits — list your active traits",
    )
    def traits_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        service.list_traits(ctx)

    @registry.register(
        "skills",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="skills — list your skills and their levels",
    )
    def skills_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        service.list_skills(ctx)

    @registry.register(
        "reputation",
        "rep",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="reputation — list your standing with NPCs and factions",
    )
    def reputation_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        service.list_reputation(ctx)

    @registry.register(
        "score",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="score — your progress: level/xp, quests, wealth, reputation, discoveries",
    )
    def score_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        service.score(ctx)
