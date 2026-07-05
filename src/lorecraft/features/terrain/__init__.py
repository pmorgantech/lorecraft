"""Terrain feature: terrain type definitions and their registry.

Self-contained Tier 2 package (tier split, step 8): the terrain defs/registry
live in `definitions.py` (registered on import — static data, idempotent by
key). Passive manifest.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="terrain", name="Terrain")

register_feature(manifest)
