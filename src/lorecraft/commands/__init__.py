"""Command composition root.

After the tier split (step 9), each feature owns its verbs in
``lorecraft.features.<feature>.commands``; only the shell/out-of-character
commands (``meta``, ``social``, ``news``, ``report``) still live in this
package, because they span concerns (help/quit/save, say/talk, /news, /report)
rather than belonging to one Tier 2 feature. ``register_all_commands`` is the
composition point that wires the engine's shell verbs together with every
feature's verbs into a single ``CommandRegistry`` — a legitimate composition
concern (it may import features; the engine may not import it). Feature-gated
verbs (fatigue/economy/bank) register only when their service is present.
"""

from lorecraft.features.bank.commands import register_bank_commands
from lorecraft.features.character.commands import register_character_commands
from lorecraft.features.combat.commands import register_combat_commands
from lorecraft.features.fatigue.commands import register_condition_commands
from lorecraft.features.follow.commands import register_follow_commands
from lorecraft.features.context_commands.commands import register_context_commands
from lorecraft.features.hunts.commands import register_hunt_commands
from lorecraft.features.marks.commands import register_mark_commands
from lorecraft.features.consumables.commands import register_consumable_commands
from lorecraft.features.economy.commands import register_economy_commands
from lorecraft.features.exploration.commands import register_exploration_commands
from lorecraft.features.inventory.commands import register_inventory_commands
from lorecraft.features.quests.commands import register_quest_commands
from lorecraft.features.disciplines.commands import register_discipline_commands
from lorecraft.commands.meta import register_meta_commands
from lorecraft.features.movement.commands import register_movement_commands
from lorecraft.commands.news import register_news_commands
from lorecraft.commands.report import register_report_commands
from lorecraft.commands.social import register_social_commands
from lorecraft.features.trading.commands import register_trade_commands
from lorecraft.features.transit.commands import register_transit_commands
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.services.container import ServiceContainer
from lorecraft.features.transit.service import TransitService


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
    # Tier 1 shell/engine verbs — always registered. Each module's verbs are
    # labelled with a help category here (one source of truth) via the
    # `registry.category(...)` context, so the help system can group them.
    with registry.category("system"):
        register_meta_commands(registry, services.save)
        register_news_commands(registry)
        register_report_commands(registry)
    # Feature-gated: register a feature's verbs only when its service exists
    # (i.e. the owning Tier 2 feature is enabled — see ServiceContainer.build).
    if services.movement is not None:
        with registry.category("movement"):
            register_movement_commands(registry, services.movement)
    if services.follow is not None:
        with registry.category("movement"):
            register_follow_commands(registry, services.follow)
    if services.inventory is not None:
        with registry.category("inventory"):
            register_inventory_commands(registry, services.inventory)
    if services.consumables is not None:
        with registry.category("inventory"):
            register_consumable_commands(registry, services.consumables)
    if services.dialogue is not None:
        with registry.category("social"):
            register_social_commands(registry, services.dialogue)
    if services.quest is not None:
        with registry.category("quests"):
            register_quest_commands(registry)
    # Discipline verbs (train/learn/abilities) — always on; they read the ability
    # registry, which is simply empty when no ability content is loaded.
    with registry.category("disciplines"):
        register_discipline_commands(registry)
    if services.character_info is not None:
        with registry.category("character"):
            register_character_commands(registry, services.character_info)
    if services.exploration is not None and services.journal is not None:
        with registry.category("exploration"):
            register_exploration_commands(
                registry, services.exploration, services.journal
            )
    if services.fatigue is not None:
        with registry.category("condition"):
            register_condition_commands(registry, services.fatigue)
    if services.economy is not None:
        with registry.category("economy"):
            register_economy_commands(registry, services.economy)
    if services.bank is not None:
        with registry.category("banking"):
            register_bank_commands(registry, services.bank)
    if services.combat is not None:
        with registry.category("combat"):
            register_combat_commands(registry, services.combat)
    if services.combat is not None or services.follow is not None:
        with registry.category("movement"):
            _register_assist_command(registry, services)
    if services.trade is not None:
        with registry.category("trading"):
            register_trade_commands(registry, services.trade)
    if services.hunts is not None:
        with registry.category("exploration"):
            register_hunt_commands(registry, services.hunts)
    if services.marks is not None:
        with registry.category("exploration"):
            register_mark_commands(registry, services.marks)
    if transit is not None:
        with registry.category("transit"):
            register_transit_commands(registry, transit)
    # Context-attached verbs (Sprint 55) last, so their collision check sees
    # every built-in verb already registered. The context registry is empty
    # unless the feature loaded world content, so this is a no-op otherwise.
    register_context_commands(registry)


def _register_assist_command(
    registry: CommandRegistry, services: ServiceContainer
) -> None:
    @registry.register(
        "assist",
        help="assist <player> — follow an ally, or join their combat if they are fighting",
    )
    def assist_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            ctx.say("Assist whom?", MessageType.WARNING)
            return
        if services.combat is not None and _should_combat_assist(noun, ctx):
            services.combat.assist(noun, ctx)
            return
        if services.follow is not None:
            services.follow.follow(noun, ctx)
            return
        if services.combat is not None:
            services.combat.assist(noun, ctx)
            return
        ctx.say("There is no one here to assist.", MessageType.WARNING)


def _should_combat_assist(noun: str, ctx: GameContext) -> bool:
    if ctx.player.active_combat_session_id:
        return True
    target = ctx.player_repo.by_username(noun)
    return (
        target is not None
        and target.current_room_id == ctx.room.id
        and bool(target.active_combat_session_id)
    )
