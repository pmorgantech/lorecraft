"""Combat status-effect definitions built on the engine ActiveEffect primitive."""

from __future__ import annotations

from lorecraft.engine.game.effects import EffectDef, get_registry

COMBAT_OFF_BALANCE = "combat.off_balance"


def register_combat_effects() -> None:
    """Register combat-owned status effects with the generic effect registry."""

    registry = get_registry()
    if registry.get(COMBAT_OFF_BALANCE) is None:
        registry.register(
            EffectDef(
                key=COMBAT_OFF_BALANCE,
                modifiers=lambda effect: [],
            )
        )
