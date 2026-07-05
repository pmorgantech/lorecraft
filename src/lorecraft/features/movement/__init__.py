"""Movement feature: room-to-room movement with locks, terrain gating, and
skill checks.

Self-contained Tier 2 package (tier split, step 8): `MovementService` lives in
`service.py`. It is Tier 2 rather than an engine primitive because movement is
terrain-gated and skill-checked — `move()` reads the terrain registry and runs
a skill check on the traversing skill, so it depends on the `terrain` and
`skills` features. Passive manifest — the service is built by the
`ServiceContainer`; the movement command module co-locates here in step 9.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="movement", name="Movement")

register_feature(manifest)
