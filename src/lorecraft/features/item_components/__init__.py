"""Item components feature: the standard item component defs — durability,
openable, lit, container, mechanism.

Self-contained Tier 2 package (tier split, step 8): the standard component defs
live in `components.py`, wired by the manifest. These defs are shared
foundations that other features (containers, light, mechanism puzzles) build
on, so several of those depend on this feature. (The generic per-instance
component-state accessor is a Tier 1 primitive in
`lorecraft.engine.services.item_components`, distinct from these defs.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.item_components.components import (
    register as _register_components,
)

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_components()


manifest = FeatureManifest(
    key="item_components", name="Standard Item Components", register_fn=_wire
)

register_feature(manifest)
