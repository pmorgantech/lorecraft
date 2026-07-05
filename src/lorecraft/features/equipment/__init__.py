"""Equipment feature: equipped-item modifier/trait sources + the player
equip-slot move validator.

Self-contained Tier 2 package (tier split, step 8): its slot defs (`slots.py`),
modifier/trait sources (`sources.py`), and equip-slot move validator
(`validators.py`) live here, wired by the manifest. Depends on `traits` because
the equipment trait source registers on the trait registry that feature owns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.equipment.sources import register as _register_equipment_source
from lorecraft.features.equipment.validators import (
    register as _register_equipment_validators,
)

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_equipment_source()
    _register_equipment_validators()


manifest = FeatureManifest(
    key="equipment",
    name="Equipment",
    dependencies=("traits",),
    register_fn=_wire,
)

register_feature(manifest)
