"""Containers feature: the container move validator (open state, capacity,
nesting depth).

Migrated to the manifest system (tier split, step 5). Registration still lives
in `lorecraft.game.container_validators`; the manifest wraps it. Depends on
`item_components` because containers rely on the "container"/"openable"
component defs that feature registers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.game.container_validators import register as _register_containers

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_containers()


manifest = FeatureManifest(
    key="containers",
    name="Containers",
    dependencies=("item_components",),
    register_fn=_wire,
)

register_feature(manifest)
