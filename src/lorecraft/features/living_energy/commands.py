"""Living-energy commands: the `harvest <channel>` verb + flavor aliases
(roadmap_world.md gap #2).

`harvest` is an *active ability* (flavor A) unlocked by the skill tree: every verb
here registers with `conditions=[..., actor_has_flag:ability.harvest]`, so they are
invisible and unusable — hidden from `help` too — until the node is bought.

`harvest <channel>` takes an explicit channel; the flavor aliases pre-fill it
(`tap` -> lumenroot, `scrape` -> dreamveil, `bleed` -> emberthorn), matching each
channel's real-world harvesting verb from the lore.
"""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.engine.services.zone_energy import ZoneEnergyService
from lorecraft.features.living_energy.channels import CHANNELS
from lorecraft.features.living_energy.harvest import HarvestService
from lorecraft.types import CommandHandler

# Ability gate: the verb is available — and `help`-listed — only once the player
# holds `ability.harvest` (set by training the skill-tree node). Same
# `actor_has_flag:<flag>` gating mechanism forage/sense use.
_HARVEST_GATE = "actor_has_flag:ability.harvest"

# Flavor aliases -> the channel each pre-fills, drawn from the lore's harvesting
# verbs (tap the sap, scrape the gel, bleed the vitriol).
_ALIAS_CHANNELS: dict[str, str] = {
    "tap": "lumenroot",
    "scrape": "dreamveil",
    "bleed": "emberthorn",
}


def register_living_energy_commands(
    registry: CommandRegistry,
    harvest: HarvestService | None = None,
    *,
    zone_energy: ZoneEnergyService | None = None,
) -> None:
    # `zone_energy` is the engine-backed singleton built in `main.py` when the
    # feature is enabled; inject it so `harvest` shares the same instance running
    # the drift sweep (mirrors how `transit`/`MeterService` are threaded in).
    harvest_service = harvest or HarvestService(zone_energy=zone_energy)

    _channels = ", ".join(CHANNELS)

    @registry.register(
        "harvest",
        conditions=[
            CommandCondition.REQUIRES_LIGHT,
            CommandCondition.NOT_IN_COMBAT,
            _HARVEST_GATE,
        ],
        help=(
            "harvest <channel> — draw living energy from an energy-rich zone "
            f"({_channels}); requires the Harvest ability"
        ),
    )
    def harvest_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            ctx.say(f"Harvest what? ({_channels})", MessageType.WARNING)
            return
        harvest_service.harvest(ctx, noun.strip().lower())

    def _make_alias(channel: str) -> CommandHandler:
        def alias_command(noun: str | None, ctx: GameContext) -> None:
            del noun  # channel is fixed by the alias
            harvest_service.harvest(ctx, channel)

        return alias_command

    for alias, channel in _ALIAS_CHANNELS.items():
        registry.register(
            alias,
            conditions=[
                CommandCondition.REQUIRES_LIGHT,
                CommandCondition.NOT_IN_COMBAT,
                _HARVEST_GATE,
            ],
            help=(
                f"{alias} — harvest {channel} living energy from a rich zone "
                "(requires the Harvest ability)"
            ),
        )(_make_alias(channel))
