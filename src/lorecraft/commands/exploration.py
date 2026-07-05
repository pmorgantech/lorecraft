"""Exploration commands: search, journal (Sprint 25)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.services.exploration import ExplorationService
from lorecraft.services.journal import JournalService


def register_exploration_commands(
    registry: CommandRegistry,
    exploration: ExplorationService | None = None,
    journal: JournalService | None = None,
) -> None:
    exploration_service = exploration or ExplorationService()
    journal_service = journal or JournalService()

    @registry.register(
        "search",
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
        help="search — look for hidden exits and secrets in the room",
    )
    def search_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        exploration_service.search(ctx)

    @registry.register(
        "journal",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="journal — review places visited, people met, lore learned, and active quests",
    )
    def journal_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        journal_service.show(ctx)
