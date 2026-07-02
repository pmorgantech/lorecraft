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
        help="look — describe your surroundings",
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
        help="take <item> — pick up an item (also: 2 <item>, all <item>)",
    )
    def take_command(noun: str | None, ctx: object) -> None:
        service.take_item(noun, cast(GameContext, ctx))

    @registry.register(
        "drop",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="drop <item> — put down a carried item",
    )
    def drop_command(noun: str | None, ctx: object) -> None:
        service.drop_item(noun, cast(GameContext, ctx))

    @registry.register(
        "examine",
        "inspect",
        "x",
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
        help="examine <item> — read an item's description",
    )
    def examine_command(noun: str | None, ctx: object) -> None:
        service.examine(noun, cast(GameContext, ctx))

    @registry.register(
        "inventory",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="inventory — list what you are carrying",
    )
    def inventory_command(noun: str | None, ctx: object) -> None:
        del noun
        service.inventory(cast(GameContext, ctx))

    @registry.register(
        "use",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="use <item> [on/with <other>] — use an item, optionally combined with another",
    )
    def use_command(noun: str | None, ctx: object) -> None:
        service.use_item(noun, cast(GameContext, ctx))

    @registry.register(
        "give",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="give <item> to <name> — hand a carried item to an NPC",
    )
    def give_command(noun: str | None, ctx: object) -> None:
        service.give_item(noun, cast(GameContext, ctx))
