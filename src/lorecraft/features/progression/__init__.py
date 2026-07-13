"""Progression feature: XP/leveling *policy* — the Tier 2 opinionated layer.

Owns the admin-tunable `ProgressionConfig` singleton (XP-curve params + per-level
reward policy) that feeds the Tier 1 `engine.game.leveling` mechanism. This
package is where "what does a level grant" is decided and made data-driven —
seeded from `world.yaml`, live-editable via the admin console (Sprint 73.4).

Sprint 73 ships the config + reward interpreter + level-up wiring. The skill
tree / skill-point sink and its passive-ability modifier source moved to the
`disciplines` feature in Sprint 78, so this is now a passive manifest — leveling
policy is consumed directly by `engine.game.leveling`, nothing to wire here.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(
    key="progression",
    name="Progression & Leveling",
)

register_feature(manifest)
