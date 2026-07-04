"""Fatigue feature: the "fatigue" meter and its skill-check penalty modifier.

Migrated to the manifest system (tier split, step 5). Registration still lives
in `lorecraft.game.fatigue_source`; the manifest wraps it so it loads via config
instead of a side-effect import in main.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.game.fatigue_source import register as _register_fatigue

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_fatigue()


manifest = FeatureManifest(key="fatigue", name="Fatigue", register_fn=_wire)

register_feature(manifest)
