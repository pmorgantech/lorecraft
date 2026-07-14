"""Character condition commands: rest, sleep, camp (Sprint 27.1)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.features.fatigue.service import FatigueService


def register_condition_commands(
    registry: CommandRegistry, fatigue: FatigueService | None = None
) -> None:
    fatigue_service = fatigue or FatigueService()

    @registry.register(
        "rest",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="rest — enter rest mode and recover movement points over time",
    )
    def rest_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        fatigue_service.rest(ctx)

    @registry.register(
        "stand",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="stand — leave rest mode",
    )
    def stand_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        fatigue_service.stand(ctx)

    @registry.register(
        "camp",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="camp — make camp and recover a good deal of stamina",
    )
    def camp_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        fatigue_service.camp(ctx)

    @registry.register(
        "sleep",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="sleep <hours> — sleep deeply and recover movement points faster",
    )
    def sleep_command(noun: str | None, ctx: GameContext) -> None:
        hours: float | None = None
        if noun is not None:
            try:
                hours = float(noun)
            except ValueError:
                ctx.say("Sleep for how many hours? Try `sleep 8`.", MessageType.WARNING)
                return
        fatigue_service.sleep(ctx, hours)
