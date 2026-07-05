"""Exploration feature: exit-discovery helpers, the exploration service, and
the exploration journal.

Self-contained Tier 2 package (tier split, step 8): exit-discovery helpers in
`rules.py`, the exploration service in `service.py`, and the journal in
`journal.py`, wired through the `ServiceContainer`. Passive manifest: it
registers nothing on the shared registries, so it has no `register_fn`.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="exploration", name="Exploration & Journal")

register_feature(manifest)
