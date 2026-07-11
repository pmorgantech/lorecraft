"""Consumables feature: the eat/drink/quaff verbs and their item effects.

Self-contained Tier 2 package. The `ConsumableService` (`service.py`) consumes a
held food/drink item and fires its one-shot `heal`/`apply_effect` descriptors
(`effects.py`); its `register_fn` registers the positive buff EffectDefs those
`apply_effect` descriptors reference (`buffs.py`). Depends on the `inventory`
feature for shared held-item resolution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.consumables.buffs import register as _register_buffs
from lorecraft.features.manifest import FeatureManifest, register_feature

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_buffs()


manifest = FeatureManifest(
    key="consumables",
    name="Consumables (eat/drink)",
    dependencies=("inventory",),
    register_fn=_wire,
)

register_feature(manifest)
