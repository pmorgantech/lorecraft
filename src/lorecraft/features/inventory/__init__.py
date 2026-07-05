"""Inventory feature: take/drop/get/put/give item management.

Self-contained Tier 2 package (tier split, step 8): the inventory service lives
in `service.py`. Passive manifest — `InventoryService` is built by the
`ServiceContainer` (its inventory command module dissolves in step 9).
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="inventory", name="Inventory")

register_feature(manifest)
