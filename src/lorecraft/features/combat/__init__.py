"""Combat feature: Scheduled Intent combat foundation."""

from __future__ import annotations

from lorecraft.features.combat.effects import register_combat_effects
from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.state import AppState


def register_combat_feature(state: AppState) -> None:
    del state
    register_combat_effects()


manifest = FeatureManifest(
    key="combat",
    name="Combat",
    dependencies=("fatigue",),
    register_fn=register_combat_feature,
)

register_feature(manifest)
