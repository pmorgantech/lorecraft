"""Trading feature: player-to-player trade offers.

Self-contained Tier 2 package (tier split, step 8): service (`service.py`),
tables (`models.py` — `TradeOffer`, plus `PvpConsent` which rides along until
PvP is built), repo (`repo.py`). Passive manifest — `TradeService` is built by
the `ServiceContainer` (its trade command module dissolves in step 9).
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="trading", name="Trading")

register_feature(manifest)
