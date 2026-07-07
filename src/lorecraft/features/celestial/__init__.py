"""Celestial feature: moon phase + tide as content-facing world state (Sprint 54).

Self-contained Tier 2 package over the Tier 1 celestial calendar
(`engine/clock/celestial.py`): `handlers.py` emits
`MOON_PHASE_CHANGED`/`TIDE_CHANGED` off the existing day/hour clock events
(the weather-handler pattern); `conditions.py` registers the
`moon_phase_is`/`tide_is` gates with the command + dialogue condition
registries. No new model, no new scheduler — pure derivation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.celestial.conditions import register as _register_conditions

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_conditions()


manifest = FeatureManifest(key="celestial", name="Celestial Cycles", register_fn=_wire)

register_feature(manifest)
