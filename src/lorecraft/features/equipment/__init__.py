"""Equipment feature: equipped-item modifier/trait sources + the player
equip-slot move validator.

Migrated to the manifest system (tier split, step 5). Registration still lives
in `lorecraft.game.equipment_source` and `lorecraft.game.equipment_validators`;
the manifest wraps both. Depends on `traits` because the equipment trait source
registers on the trait registry that the traits feature owns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.game.equipment_source import register as _register_equipment_source
from lorecraft.game.equipment_validators import (
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
