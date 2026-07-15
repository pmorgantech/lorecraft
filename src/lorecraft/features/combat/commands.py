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
        "defend",
        "guard",
        conditions=["in_combat"],
        help="defend — spend your next action bracing against attacks",
    )
    def defend_command(noun: str | None, ctx: GameContext) -> None:
        service.defend(noun, ctx)

    @registry.register(
        "flee",
        conditions=["in_combat"],
        help="flee — commit to an escape attempt from the current encounter",
    )
    def flee_command(noun: str | None, ctx: GameContext) -> None:
        service.flee(noun, ctx)
