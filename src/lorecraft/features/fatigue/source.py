"""Fatigue Meter definition + skill-check penalty ModifierSource (Sprint 27.1).

"fatigue" is a Meter (engine_core.md §3.3) holding remaining stamina: starts
full, drains with travel/encumbrance (services/fatigue.py), restored by
resting. This module registers the MeterDef and the other half of the
mechanic -- once stamina runs low it saps every registered skill check via a
flat `mult` penalty (docs/wishlist.md's "low fatigue penalizes skill
checks"). Self-registers at import time, imported for side effects from
main.py, mirroring game/equipment_source.py / game/standard_traits.py.
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.engine.game import meters as meters_module
from lorecraft.engine.game import modifiers as modifiers_module
from lorecraft.features.disciplines.abilities import get_discipline_registry
from lorecraft.engine.game.meters import MeterDef
from lorecraft.engine.game.modifiers import Modifier
from lorecraft.engine.models.player import PlayerStats
from lorecraft.engine.repos.meter_repo import MeterRepo

FATIGUE_METER_KEY = "fatigue"

# Stamina ratio (current / maximum) thresholds below which skill checks
# suffer a flat penalty. No meter row yet == never drained == fully rested,
# so an absent row contributes no penalty.
WEARY_RATIO = 0.5
EXHAUSTED_RATIO = 0.2
WEARY_MULT = 0.9
EXHAUSTED_MULT = 0.65


def fatigue_base_maximum(entity_type: str, entity_id: str, session: Session) -> float:
    """base_maximum for the "fatigue" MeterDef -- scales with fortitude,
    the survival skill's governing stat (game/skills.py)."""
    if entity_type == "player":
        stats = session.get(PlayerStats, entity_id)
        fortitude = stats.fortitude if stats is not None else 10
        return 50.0 + 5.0 * fortitude
    return 100.0


class FatigueModifierSource:
    """ModifierSource applying a low-stamina penalty to every registered skill."""

    def modifiers_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> list[Modifier]:
        if entity_type != "player":
            return []
        meter = MeterRepo(session).find(entity_type, entity_id, FATIGUE_METER_KEY)
        if meter is None or meter.maximum <= 0:
            return []
        ratio = meter.current / meter.maximum
        if ratio < EXHAUSTED_RATIO:
            mult = EXHAUSTED_MULT
        elif ratio < WEARY_RATIO:
            mult = WEARY_MULT
        else:
            return []
        # Sap every live skill check. The check identities are the `skill.<name>`
        # resolver keys each discipline declares it governs (§6.1, Option A) — a
        # data-driven replacement for iterating the deleted flat skill catalogue.
        return [
            Modifier(key=check_key, kind="mult", amount=mult, source="fatigue")
            for discipline in get_discipline_registry().all()
            for check_key in discipline.check_keys
        ]


_registered = False


def register() -> None:
    """Register the "fatigue" meter + its skill-check penalty modifier source.
    Called by the `fatigue` feature manifest when enabled (no longer a
    module-level import side effect). Idempotent (the modifier source is
    appended to a list, so a guard prevents double-registration)."""
    global _registered
    meter_registry = meters_module.get_registry()
    already_registered = _registered
    if already_registered and FATIGUE_METER_KEY in meter_registry:
        return
    _registered = True
    meter_registry.register(
        MeterDef(key=FATIGUE_METER_KEY, base_maximum=fatigue_base_maximum)
    )
    if not already_registered:
        modifiers_module.get_registry().register(FatigueModifierSource())
