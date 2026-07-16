"""Inventory and room inspection commands."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.features.inventory.service import InventoryService


def register_inventory_commands(
    registry: CommandRegistry, inventory_service: InventoryService | None = None
) -> None:
    service = inventory_service or InventoryService()

    @registry.register(
        "look",
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
        help="look — describe your surroundings",
    )
    def look_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            service.look(ctx)
            return
        service.examine(noun, ctx)

    @registry.register(
        "take",
        "get",
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
        help="take <item> [from <container>] — pick up an item (also: get, 2 <item>, all <item>)",
    )
    def take_command(noun: str | None, ctx: GameContext) -> None:
        service.take_from_item(noun, ctx)

    @registry.register(
        "drop",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="drop <item> — put down a carried item",
    )
    def drop_command(noun: str | None, ctx: GameContext) -> None:
        service.drop_item(noun, ctx)

    @registry.register(
        "examine",
        "inspect",
        "x",
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
        help="examine <item> — read an item's description",
    )
    def examine_command(noun: str | None, ctx: GameContext) -> None:
        service.examine(noun, ctx)

    @registry.register(
        "inventory",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="inventory — list what you are carrying",
    )
    def inventory_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        service.inventory(ctx)

    @registry.register(
        "use",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="use <item> [on/with <other>] — use an item, optionally combined with another",
    )
    def use_command(noun: str | None, ctx: GameContext) -> None:
        service.use_item(noun, ctx)

    @registry.register(
        "give",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="give <item> to <name> — hand a carried item to an NPC",
    )
    def give_command(noun: str | None, ctx: GameContext) -> None:
        service.give_item(noun, ctx)

    @registry.register(
        "open",
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
        help="open <container> — open a container",
    )
    def open_command(noun: str | None, ctx: GameContext) -> None:
        service.open_item(noun, ctx)

    @registry.register(
        "close",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="close <container> — close a container",
    )
    def close_command(noun: str | None, ctx: GameContext) -> None:
        service.close_item(noun, ctx)

    @registry.register(
        "activate",
        "turn",
        "pull",
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
        help="turn/pull/activate <lever or dial> — cycle a mechanism's state",
    )
    def activate_command(noun: str | None, ctx: GameContext) -> None:
        service.activate_mechanism(noun, ctx)

    @registry.register(
        "wear",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="wear <item> — equip a worn item (armor, clothing)",
    )
    def wear_command(noun: str | None, ctx: GameContext) -> None:
        service.wear_item(noun, ctx)

    @registry.register(
        "remove",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="remove <item> — unequip a worn item",
    )
    def remove_command(noun: str | None, ctx: GameContext) -> None:
        service.remove_item(noun, ctx)

    @registry.register(
        "wield",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="wield <item> — equip a wielded item (weapon, tool, light)",
    )
    def wield_command(noun: str | None, ctx: GameContext) -> None:
        service.wield_item(noun, ctx)

    @registry.register(
        "unwield",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="unwield <item> — unequip a wielded item",
    )
    def unwield_command(noun: str | None, ctx: GameContext) -> None:
        service.unwield_item(noun, ctx)

    @registry.register(
        "equipment",
        "eq",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="equipment — list what you are wearing and wielding",
    )
    def equipment_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        service.list_equipment(ctx)

    @registry.register(
        "body",
        "condition",
        help="body — show worn equipment and body condition by body part",
    )
    def body_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        service.body(ctx)

    @registry.register(
        "put",
        conditions=[CommandCondition.REQUIRES_LIGHT, CommandCondition.NOT_IN_COMBAT],
        help="put <item> in <container> — place a carried item into a container",
    )
    def put_command(noun: str | None, ctx: GameContext) -> None:
        service.put_item(noun, ctx)

    @registry.register(
        "light",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="light <item> — light a light source (lantern, torch)",
    )
    def light_command(noun: str | None, ctx: GameContext) -> None:
        service.light_item(noun, ctx)

    @registry.register(
        "extinguish",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="extinguish <item> — put out a lit light source",
    )
    def extinguish_command(noun: str | None, ctx: GameContext) -> None:
        service.extinguish_item(noun, ctx)
