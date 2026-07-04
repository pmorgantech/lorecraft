"""Command registration helpers."""

from lorecraft.commands.bank import register_bank_commands
from lorecraft.commands.character import register_character_commands
from lorecraft.commands.condition import register_condition_commands
from lorecraft.commands.economy import register_economy_commands
from lorecraft.commands.exploration import register_exploration_commands
from lorecraft.commands.inventory import register_inventory_commands
from lorecraft.commands.meta import register_meta_commands
from lorecraft.commands.movement import register_movement_commands
from lorecraft.commands.news import register_news_commands
from lorecraft.commands.social import register_social_commands
from lorecraft.commands.trade import register_trade_commands
from lorecraft.game.registry import CommandRegistry
from lorecraft.services.container import ServiceContainer


def register_all_commands(
    registry: CommandRegistry, services: ServiceContainer | None = None
) -> None:
    """Register every command module's verbs, wiring in gameplay services.

    Defaults to a fresh `ServiceContainer` when none is supplied (standalone
    router use, tests). Production entry points build one container in
    `AppState` and pass it in so every command uses the same service
    instances.
    """
    services = services or ServiceContainer.build()
    register_meta_commands(registry, services.save)
    register_movement_commands(registry, services.movement)
    register_inventory_commands(registry, services.inventory)
    register_social_commands(registry, services.dialogue)
    register_news_commands(registry)
    register_character_commands(registry, services.character_info)
    register_exploration_commands(registry, services.exploration, services.journal)
    register_condition_commands(registry, services.fatigue)
    register_economy_commands(registry, services.economy)
    register_bank_commands(registry, services.bank)
    register_trade_commands(registry, services.trade)
