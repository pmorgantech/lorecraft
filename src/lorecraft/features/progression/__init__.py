"""Progression feature: XP/leveling *policy* — the Tier 2 opinionated layer.

Owns the admin-tunable `ProgressionConfig` singleton (XP-curve params + per-level
reward policy) that feeds the Tier 1 `engine.game.leveling` mechanism. This
package is where "what does a level grant" is decided and made data-driven —
seeded from `world.yaml`, live-editable via the admin console (Sprint 73.4).

Sprint 73 ships the config + reward interpreter + level-up wiring. Sprint 74
adds the skill tree (the skill-point *sink*): the `register_fn` binds the
passive-ability modifier source onto the Tier 1 modifier resolver.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.progression.modifier_source import (
    register as _register_modifiers,
)

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    # Bridge unlocked passive-ability nodes (Sprint 74.4) into the modifier resolver.
    _register_modifiers()


manifest = FeatureManifest(
    key="progression",
    name="Progression & Leveling",
    register_fn=_wire,
)

register_feature(manifest)
