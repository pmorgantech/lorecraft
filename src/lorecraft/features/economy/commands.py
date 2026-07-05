"""Vendor shop commands: list/shop, buy, sell, appraise (Sprint 28.1)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.features.economy.service import EconomyService


def register_economy_commands(
    registry: CommandRegistry, economy: EconomyService | None = None
) -> None:
    service = economy or EconomyService()

    @registry.register(
        "list",
        "shop",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="list — show a room's shop stock and prices (also: shop)",
    )
    def list_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        service.list_shop(ctx)

    @registry.register(
        "buy",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="buy <item> [qty] — purchase an item from a room's shop",
    )
    def buy_command(noun: str | None, ctx: GameContext) -> None:
        service.buy(noun, ctx)

    @registry.register(
        "sell",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="sell <item> [qty] — sell a carried item to a room's shop",
    )
    def sell_command(noun: str | None, ctx: GameContext) -> None:
        service.sell(noun, ctx)

    @registry.register(
        "appraise",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="appraise <item> — estimate an item's coin value",
    )
    def appraise_command(noun: str | None, ctx: GameContext) -> None:
        service.appraise(noun, ctx)
