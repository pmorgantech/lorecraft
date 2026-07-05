"""Transit feature: vehicles/lines/stops running on scheduled routes.

Self-contained Tier 2 package (tier split, step 8): service (`service.py`),
tables (`models.py`), repo (`repo.py`). Passive manifest — `TransitService`
needs the live engine/mobile-route service, so it is constructed from `main.py`
(its transit command module dissolves into the package in step 9).
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="transit", name="Transit")

register_feature(manifest)
