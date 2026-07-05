"""Containers feature: the container move validator (open state, capacity,
nesting depth).

Self-contained Tier 2 package (tier split, step 8): the container move
validator lives in `validators.py`, wired by the manifest. Depends on
`item_components` because containers rely on the "container"/"openable"
component defs that feature registers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.containers.validators import register as _register_containers

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
