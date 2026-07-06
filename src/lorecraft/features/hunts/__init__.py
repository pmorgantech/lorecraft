"""Scavenger-hunt feature: time-boxed find-the-items world events (Sprint 48).

Self-contained Tier 2 package built entirely on existing primitives (item
spawns, the `ITEM_TAKEN` event, player flags, the ledger, news) — no new Tier 1
mechanism. `models.py` holds the YAML-authored hunt definitions + registry +
content-lint; `service.py` runs the open/find/reward/close lifecycle;
`commands.py` adds a read-only `hunts` verb. See `docs/scavenger_hunt.md`.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="hunts", name="Scavenger Hunts")

register_feature(manifest)
