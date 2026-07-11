"""Consumable verbs: eat, drink (and its `quaff` alias)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.features.consumables.service import ConsumableService


def register_consumable_commands(
    registry: CommandRegistry, consumable_service: ConsumableService | None = None
) -> None:
    service = consumable_service or ConsumableService()

    @registry.register(
        "eat",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="eat <item> — consume a carried food item",
    )
    def eat_command(noun: str | None, ctx: GameContext) -> None:
        service.eat(noun, ctx)

    @registry.register(
        "drink",
        "quaff",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="drink/quaff <item> — consume a carried drink or potion",
    )
    def drink_command(noun: str | None, ctx: GameContext) -> None:
        service.drink(noun, ctx)
