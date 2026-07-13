"""Exploration commands: search, journal (Sprint 25), forage + sense (Sprint 74)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.features.exploration.forage import ForageService
from lorecraft.features.exploration.service import ExplorationService
from lorecraft.features.exploration.journal import JournalService

# Ability gates (Sprint 74): the verb is available — and `help`-listed — only
# once the player holds the matching `ability.<id>` flag (set by training the
# skill-tree node). Expressed as `actor_has_flag:<flag>` colon-strings, the
# gating mechanism the design mandates (no new condition needed).
_FORAGE_GATE = "actor_has_flag:ability.forage"


def register_exploration_commands(
    registry: CommandRegistry,
    exploration: ExplorationService | None = None,
    journal: JournalService | None = None,
    forage: ForageService | None = None,
) -> None:
    exploration_service = exploration or ExplorationService()
    journal_service = journal or JournalService()
    forage_service = forage or ForageService()

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

    @registry.register(
        "forage",
        conditions=[
            CommandCondition.REQUIRES_LIGHT,
            CommandCondition.NOT_IN_COMBAT,
            _FORAGE_GATE,
        ],
        help="forage — search the wild outdoors for something edible (requires the Forage ability)",
    )
    def forage_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        forage_service.forage(ctx)
