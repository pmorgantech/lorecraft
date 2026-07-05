"""Skills feature: the skill definitions/registry and the use-based skill
improvement service.

Self-contained Tier 2 package (tier split, step 8): the skill defs live in
`definitions.py` (registered on import — pure static data, idempotent by key,
imported directly by their consumers) and the improvement service in
`service.py`. Passive manifest: it registers nothing on the shared registries
beyond those defs, so it has no `register_fn`.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="skills", name="Skills")

register_feature(manifest)
