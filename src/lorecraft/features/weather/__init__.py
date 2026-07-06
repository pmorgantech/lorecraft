"""Weather feature: weather/season transitions on the world clock, and the
weather-driven terrain-difficulty modifier (Sprint 44).

Self-contained Tier 2 package (tier split, step 8): the weather handlers live in
`handlers.py`; the Sprint 44 `WeatherTerrainModifierSource` in `modifiers.py`
(imported here so its §3.5 registration runs). Passive manifest —
`register_weather_handlers` still needs the live bus/engine/rng, so it is wired
from `main.py` alongside the other runtime services.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.weather import modifiers as _modifiers  # noqa: F401  (registers on import)

manifest = FeatureManifest(key="weather", name="Weather & Seasons")

register_feature(manifest)
