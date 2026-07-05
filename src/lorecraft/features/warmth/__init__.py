"""Warmth feature: exposure/warmth resolution feeding the fatigue/exposure loop.

Self-contained Tier 2 package (tier split, step 8): the warmth rules live in
`rules.py`. Passive manifest — it registers nothing on the shared registries;
its helper is called directly by the features that need it (e.g. fatigue).
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="warmth", name="Warmth & Exposure")

register_feature(manifest)
