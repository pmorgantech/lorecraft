"""Fatigue feature: the "fatigue" meter and its skill-check penalty modifier.

Self-contained Tier 2 package (tier split, step 8): the meter + skill-check
penalty modifier live in `source.py` and the fatigue service in `service.py`,
wired by the manifest instead of a side-effect import in main.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.fatigue.source import register as _register_fatigue

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_fatigue()


manifest = FeatureManifest(key="fatigue", name="Fatigue", register_fn=_wire)

register_feature(manifest)
