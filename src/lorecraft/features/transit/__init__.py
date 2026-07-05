"""Transit feature: vehicles/lines/stops running on scheduled routes.

Self-contained Tier 2 package (tier split, step 8): service (`service.py`),
tables (`models.py`), repo (`repo.py`). Passive manifest — `TransitService`
needs the live engine/mobile-route service, so it is constructed from `main.py`
(its transit command module dissolves into the package in step 9).

Optional `presentation.py` (step 11): if both transit and a web host are enabled,
registers the minimap panel via the WebHost abstraction.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(
    key="transit",
    name="Transit",
    presentation="lorecraft.features.transit.presentation",
)

register_feature(manifest)
