"""Encumbrance feature: carry-weight resolution and its skill/modifier effects.

Self-contained Tier 2 package (tier split, step 8): the encumbrance rules live
in `rules.py`. Passive manifest — its helpers are called directly by inventory.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="encumbrance", name="Encumbrance")

register_feature(manifest)
