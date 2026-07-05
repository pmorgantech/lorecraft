"""Transit commands: board, disembark, schedule (Sprint 29.2)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.features.transit.service import TransitService


def register_transit_commands(
    registry: CommandRegistry, transit: TransitService | None = None
) -> None:
    if transit is None:
        return  # No engine/manager available (e.g. lightweight test registries)
    service = transit

    @registry.register(
        "board",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="board [line] — board a transit vehicle docked at this station",
    )
    def board_command(noun: str | None, ctx: GameContext) -> None:
        service.board(noun, ctx)

    @registry.register(
        "disembark",
        "leave",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="disembark — leave a transit vehicle at its current stop (also: leave)",
    )
    def disembark_command(noun: str | None, ctx: GameContext) -> None:
        service.disembark(noun, ctx)

    @registry.register(
        "schedule",
        "timetable",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="schedule [line] — show a transit line's stops and current status",
    )
    def schedule_command(noun: str | None, ctx: GameContext) -> None:
        service.schedule(noun, ctx)
