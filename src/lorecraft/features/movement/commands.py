"""Movement commands."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.features.movement.service import MovementService


CARDINAL_DIRECTIONS = ("north", "south", "east", "west")


def register_movement_commands(
    registry: CommandRegistry, movement_service: MovementService | None = None
) -> None:
    service = movement_service or MovementService()

    @registry.register(
        "go",
        *CARDINAL_DIRECTIONS,
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
        help="go <direction> — move to an adjacent room (also: north/south/east/west)",
    )
    def go_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            ctx.say("Go where?", MessageType.WARNING)
            return
        service.move(noun, ctx)

    @registry.register(
        "unlock",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="unlock <direction> — unlock an exit if you carry its key",
    )
    def unlock_command(noun: str | None, ctx: GameContext) -> None:
        service.unlock(noun, ctx)

    @registry.register(
        "lock",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="lock <direction> — lock an exit if you carry its key",
    )
    def lock_command(noun: str | None, ctx: GameContext) -> None:
        service.lock(noun, ctx)

    @registry.register(
        "pick",
        conditions=[
            CommandCondition.NOT_IN_COMBAT,
            # Sprint 74.6: available only once the Pick Locks ability is trained
            # (hidden from help until then).
            "actor_has_flag:ability.pick_locks",
        ],
        help="pick <direction> — pick a locked exit without its key (requires the Pick Locks ability)",
    )
    def pick_command(noun: str | None, ctx: GameContext) -> None:
        service.pick(noun, ctx)
