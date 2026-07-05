"""Light feature: light-source fuel consumption.

Self-contained Tier 2 package (tier split, step 8): the light/fuel service
lives in `service.py`. Passive manifest — the service needs the live engine, so
it is constructed and registered from `main.py` alongside the other runtime
services (its manifest gating is tightened in a later pass).
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="light", name="Light & Fuel")

register_feature(manifest)
