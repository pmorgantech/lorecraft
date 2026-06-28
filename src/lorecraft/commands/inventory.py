"""Inventory and room inspection commands."""

from __future__ import annotations

from typing import cast

from lorecraft.game.context import GameContext
from lorecraft.game.registry import CommandCondition, CommandRegistry
from lorecraft.services.inventory import InventoryService


def register_inventory_commands(
    registry: CommandRegistry, inventory_service: InventoryService | None = None
) -> None:
    service = inventory_service or InventoryService()

    @registry.register(
        "look",
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
    )
    def look_command(noun: str | None, ctx: object) -> None:
        game_ctx = cast(GameContext, ctx)
        if noun is None:
            service.look(game_ctx)
            return
        service.examine(noun, game_ctx)

    @registry.register(
        "take",
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
    )
    def take_command(noun: str | None, ctx: object) -> None:
        service.take_item(noun, cast(GameContext, ctx))

    @registry.register(
        "drop",
        conditions=[CommandCondition.NOT_IN_COMBAT],
    )
    def drop_command(noun: str | None, ctx: object) -> None:
        service.drop_item(noun, cast(GameContext, ctx))

    @registry.register(
        "examine",
        "inspect",
        "x",
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
    )
    def examine_command(noun: str | None, ctx: object) -> None:
        service.examine(noun, cast(GameContext, ctx))

    @registry.register("inventory", conditions=[CommandCondition.NOT_IN_COMBAT])
    def inventory_command(noun: str | None, ctx: object) -> None:
        del noun
        service.inventory(cast(GameContext, ctx))
