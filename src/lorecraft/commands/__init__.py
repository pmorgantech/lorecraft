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
from lorecraft.commands.report import register_report_commands
from lorecraft.commands.social import register_social_commands
from lorecraft.commands.trade import register_trade_commands
from lorecraft.commands.transit import register_transit_commands
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.services.container import ServiceContainer
from lorecraft.services.transit import TransitService


def register_all_commands(
    registry: CommandRegistry,
    services: ServiceContainer | None = None,
    *,
    transit: TransitService | None = None,
) -> None:
    """Register every command module's verbs, wiring in gameplay services.

    Defaults to a fresh `ServiceContainer` when none is supplied (standalone
    router use, tests). Production entry points build one container in
    `AppState` and pass it in so every command uses the same service
    instances. `transit` is separate from `ServiceContainer` (like
    `MeterService`/`MobileRouteService`, it needs the game engine +
    `ConnectionManager` at construction, not just a default no-arg build) --
    omit it to skip registering board/disembark/schedule (fine for tests that
    don't exercise transit).
    """
    services = services or ServiceContainer.build()
    register_meta_commands(registry, services.save)
    register_movement_commands(registry, services.movement)
    register_inventory_commands(registry, services.inventory)
    register_social_commands(registry, services.dialogue)
    register_news_commands(registry)
    register_report_commands(registry)
    register_character_commands(registry, services.character_info)
    register_exploration_commands(registry, services.exploration, services.journal)
    # Feature-gated: only register these verbs when their service exists (i.e.
    # the owning Tier 2 feature is enabled — see ServiceContainer.build).
    if services.fatigue is not None:
        register_condition_commands(registry, services.fatigue)
    if services.economy is not None:
        register_economy_commands(registry, services.economy)
    if services.bank is not None:
        register_bank_commands(registry, services.bank)
    register_trade_commands(registry, services.trade)
    register_transit_commands(registry, transit)
