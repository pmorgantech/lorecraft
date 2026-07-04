"""Item components feature: the standard item component defs — durability,
openable, lit, container, mechanism.

Migrated to the manifest system (tier split, step 5). Registration still lives
in `lorecraft.game.standard_components`; the manifest wraps it. These component
defs are shared foundations that other features (containers, light, mechanism
puzzles) build on, so several of those depend on this feature.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.game.standard_components import register as _register_components

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_components()


manifest = FeatureManifest(
    key="item_components", name="Standard Item Components", register_fn=_wire
)

register_feature(manifest)
