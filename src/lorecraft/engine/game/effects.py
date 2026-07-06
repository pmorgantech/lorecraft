"""Timed active-effect definitions and registry (engine_core.md §3.4).

Buffs/debuffs with clock-driven expiry — distinct from equipment effects
(last while equipped) and traits (semi-permanent). Registers itself as a
Tier 1 ModifierSource (§3.5): active effects contribute modifiers through
the same resolver equipment/traits/terrain use.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from sqlmodel import Session, select

from lorecraft.engine.game import modifiers as modifiers_module
from lorecraft.engine.game.modifiers import Modifier
from lorecraft.engine.models.meters import ActiveEffect
from lorecraft.engine.models.player import Player


@dataclass(frozen=True)
class EffectDef:
    """Definition of a registerable timed-effect type.

    Args:
        key: Unique effect identifier (e.g., "weakened").
        modifiers: (effect) -> the Modifiers this active instance contributes;
            may read `effect.payload` for magnitude.
        grants_traits: (effect) -> trait names this active instance grants.
        on_apply: (session, effect) -> transition-in side effect, called by
            EffectService.apply() after the row is flushed. For room-state
            effects (engine_core.md §3.9) this *writes the authoritative state*
            (e.g. opens an exit via RoomRepo) and stashes the prior state in
            effect.payload; on_expire restores it. Session-scoped only — must
            not message clients (architecture.md §26). Runs in the caller's
            transaction, so a raise rolls the triggering action back.
        on_expire: (session, effect) -> transition-out side effect, called by
            the expiry sweep before the row is deleted (restores what on_apply
            changed). The sweep isolates a failure and keeps the row for retry.
    """

    key: str
    modifiers: Callable[[ActiveEffect], list[Modifier]]
    grants_traits: Callable[[ActiveEffect], list[str]] = lambda effect: []  # noqa: E731
    on_apply: Callable[[Session, ActiveEffect], None] | None = None
    on_expire: Callable[[Session, ActiveEffect], None] | None = None


class EffectRegistry:
    """Registry of effect definitions, keyed by name (overwrites on re-register)."""

    def __init__(self) -> None:
        self._defs: dict[str, EffectDef] = {}

    def register(self, effect_def: EffectDef) -> None:
        self._defs[effect_def.key] = effect_def

    def get(self, key: str) -> EffectDef | None:
        return self._defs.get(key)

    def __contains__(self, key: str) -> bool:
        return key in self._defs


_registry = EffectRegistry()


def get_registry() -> EffectRegistry:
    """Get the global effect registry."""
    return _registry


def _effect_modifiers(
    session: Session, entity_type: str, entity_id: str
) -> list[Modifier]:
    """Every active effect's contributed modifiers for one entity (§3.5 input).

    Shared by both effect modifier sources so the ActiveEffect → Modifier
    translation lives in exactly one place.
    """
    statement = select(ActiveEffect).where(
        ActiveEffect.entity_type == entity_type,
        ActiveEffect.entity_id == entity_id,
    )
    modifiers: list[Modifier] = []
    for effect in session.exec(statement).all():
        effect_def = get_registry().get(effect.effect_key)
        if effect_def is not None:
            modifiers.extend(effect_def.modifiers(effect))
    return modifiers


class ActiveEffectModifierSource:
    """ModifierSource contributing an entity's *own* active-effect modifiers.

    Registered with game/modifiers.py's ModifierRegistry at this module's
    import time — the Tier 1 "active-effect" source §3.5 calls for.
    """

    def modifiers_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> Iterable[Modifier]:
        return _effect_modifiers(session, entity_type, entity_id)


class RoomAuraModifierSource:
    """ModifierSource contributing a player's *current room's* active-effect
    modifiers — occupant auras (engine_core.md §3.9).

    Read-through and keyed on the player's `current_room_id`, so an aura applies
    to whoever is in the room at resolution time and lifts the instant they
    leave — no per-player stored state, no per-tick occupant sweep. Players only
    for now; NPC occupants are a later symmetric addition.
    """

    def modifiers_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> Iterable[Modifier]:
        if entity_type != "player":
            return []
        player = session.get(Player, entity_id)
        if player is None:
            return []
        return _effect_modifiers(session, "room", player.current_room_id)


modifiers_module.get_registry().register(ActiveEffectModifierSource())
modifiers_module.get_registry().register(RoomAuraModifierSource())
