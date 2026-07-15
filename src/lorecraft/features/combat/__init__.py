"""Combat feature: Scheduled Intent combat foundation."""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.engine.game.meters import MeterDef
from lorecraft.engine.game.meters import get_registry as get_meter_registry
from lorecraft.engine.models.player import PlayerStats
from lorecraft.features.combat.effects import register_combat_effects
from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.state import AppState


def _stamina_base_maximum(entity_type: str, entity_id: str, session: Session) -> float:
    if entity_type == "player":
        stats = session.get(PlayerStats, entity_id)
        if stats is None:
            return 100.0
        return float(50 + (stats.fortitude * 5))
    return 60.0


def register_combat_feature(state: AppState) -> None:
    del state
    register_combat_effects()
    get_meter_registry().register(
        MeterDef(
            key="stamina",
            base_maximum=_stamina_base_maximum,
            regen_per_tick=5.0,
            start_full=True,
        )
    )


manifest = FeatureManifest(
    key="combat",
    name="Combat",
    register_fn=register_combat_feature,
)

register_feature(manifest)
