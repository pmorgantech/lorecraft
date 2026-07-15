"""Combat commands."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.features.combat.service import CombatService


def register_combat_commands(
    registry: CommandRegistry, combat_service: CombatService | None = None
) -> None:
    service = combat_service or CombatService()

    @registry.register(
        "attack",
        "fight",
        help="attack <target> — commit to a scheduled attack against a hostile NPC",
    )
    def attack_command(noun: str | None, ctx: GameContext) -> None:
        service.attack(noun, ctx)

    @registry.register(
        "shoot",
        "fire",
        help="shoot <target> — commit to a ranged attack against a hostile NPC",
    )
    def shoot_command(noun: str | None, ctx: GameContext) -> None:
        service.shoot(noun, ctx)

    @registry.register(
        "defend",
        conditions=["in_combat"],
        help="defend — spend your next action bracing against attacks",
    )
    def defend_command(noun: str | None, ctx: GameContext) -> None:
        service.defend(noun, ctx)

    @registry.register(
        "guard",
        conditions=["in_combat"],
        help="guard [ally] — defend yourself or intercept attacks against an ally",
    )
    def guard_command(noun: str | None, ctx: GameContext) -> None:
        service.guard(noun, ctx)

    @registry.register(
        "assist",
        help="assist <player> — join an ally's active encounter as a participant",
    )
    def assist_command(noun: str | None, ctx: GameContext) -> None:
        service.assist(noun, ctx)

    @registry.register(
        "flee",
        conditions=["in_combat"],
        help="flee — commit to an escape attempt from the current encounter",
    )
    def flee_command(noun: str | None, ctx: GameContext) -> None:
        service.flee(noun, ctx)

    @registry.register(
        "stance",
        conditions=["in_combat"],
        help="stance <balanced|aggressive|defensive|mobile> — change combat stance",
    )
    def stance_command(noun: str | None, ctx: GameContext) -> None:
        service.stance(noun, ctx)

    @registry.register(
        "reaction",
        conditions=["in_combat"],
        help="reaction <defensive|conserve|never> — set automatic reaction policy",
    )
    def reaction_command(noun: str | None, ctx: GameContext) -> None:
        service.reaction(noun, ctx)
