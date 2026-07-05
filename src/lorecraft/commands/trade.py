"""Player-to-player trade commands: offer, accept, decline (Sprint 28.4)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.services.trade import TradeService


def register_trade_commands(
    registry: CommandRegistry, trade: TradeService | None = None
) -> None:
    service = trade or TradeService()

    @registry.register(
        "offer",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="offer <item|N coins> to <player> — pledge something to a pending trade",
    )
    def offer_command(noun: str | None, ctx: GameContext) -> None:
        service.offer(noun, ctx)

    @registry.register(
        "accept",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="accept — finalize your pending trade offer",
    )
    def accept_command(noun: str | None, ctx: GameContext) -> None:
        service.accept(noun, ctx)

    @registry.register(
        "decline",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="decline — call off your pending trade offer",
    )
    def decline_command(noun: str | None, ctx: GameContext) -> None:
        service.decline(noun, ctx)
