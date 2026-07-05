"""Weather feature: weather/season transitions on the world clock.

Self-contained Tier 2 package (tier split, step 8): the weather handlers live
in `handlers.py`. Passive manifest — `register_weather_handlers` still needs
the live bus/engine/rng, so it is wired from `main.py` alongside the other
runtime services (its manifest gating is tightened in a later pass).
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="weather", name="Weather & Seasons")

register_feature(manifest)
