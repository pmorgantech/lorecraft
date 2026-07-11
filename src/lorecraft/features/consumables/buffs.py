"""Positive timed-buff EffectDefs that consumable potions apply on drink.

Small, data-referenced buffs modelled on `features/exploration/room_effects.py`:
each is a timed `EffectDef` whose `modifiers()` contributes a single positive
Modifier (§3.5), read back through the shared resolver like equipment/traits.
A buff potion in world content references one of these by `effect_key` via an
`apply_effect` consumable descriptor (see `effects.py`); the magnitude comes
from the effect payload (`{"amount": N}`), defaulting to +2.
"""

from __future__ import annotations

from lorecraft.engine.game.effects import EffectDef
from lorecraft.engine.game.effects import get_registry as get_effect_registry
from lorecraft.engine.game.modifiers import Modifier
from lorecraft.engine.models.meters import ActiveEffect

FORTIFIED_KEY = "fortified"
KEEN_MINDED_KEY = "keen_minded"

_DEFAULT_AMOUNT = 2.0


def _payload_amount(effect: ActiveEffect) -> float:
    """Read the buff magnitude from `payload["amount"]`, defaulting to +2."""
    raw = effect.payload.get("amount", _DEFAULT_AMOUNT)
    return float(raw) if isinstance(raw, (int, float)) else _DEFAULT_AMOUNT


def _fortified_modifiers(effect: ActiveEffect) -> list[Modifier]:
    """A temporary boost to raw strength (a `stat.strength` add)."""
    return [
        Modifier(
            key="stat.strength",
            kind="add",
            amount=_payload_amount(effect),
            source=f"effect:{FORTIFIED_KEY}",
        )
    ]


def _keen_minded_modifiers(effect: ActiveEffect) -> list[Modifier]:
    """A temporary boost to perception checks (a `skill.perception` add)."""
    return [
        Modifier(
            key="skill.perception",
            kind="add",
            amount=_payload_amount(effect),
            source=f"effect:{KEEN_MINDED_KEY}",
        )
    ]


def register() -> None:
    """Register the consumable buff EffectDefs.

    Idempotent: a feature's `register_fn` can run more than once (app lifespan
    re-entry in tests), so re-registration of an already-present key is skipped.
    """
    registry = get_effect_registry()
    if FORTIFIED_KEY not in registry:
        registry.register(EffectDef(key=FORTIFIED_KEY, modifiers=_fortified_modifiers))
    if KEEN_MINDED_KEY not in registry:
        registry.register(
            EffectDef(key=KEEN_MINDED_KEY, modifiers=_keen_minded_modifiers)
        )
