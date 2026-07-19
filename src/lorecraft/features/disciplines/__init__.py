"""Disciplines feature — the Tier 2 policy layer for the Discipline/Ability system.

This package is the opinionated, data-driven home for *what* disciplines and
abilities exist, what they cost, and what they grant — feeding the opinion-free
Tier 1 mechanism in `engine.game.abilities`. It ultimately replaces both
`features/skills/` (the flat skill catalog) and
`features/progression/skill_tree.py`'s node shape with one coherent model — see
`docs/engine/discipline_ability_system.md`.

Sprint 78 fills in the real feature: the `DisciplineRegistry`/`AbilityRegistry`
(loaded from `world_content/disciplines.yaml` + `abilities.yaml`), the
`ProficiencyService`/`AbilityService`, and the `train`/`disciplines`/`abilities`
commands. The `register_fn` binds the passive-ability modifier source onto the
Tier 1 modifier resolver (ported from progression 74.4). It imports only
`engine.*` and other features (never a web host), per the tier boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.disciplines.modifier_source import (
    register as _register_modifiers,
)
from lorecraft.features.manifest import FeatureManifest, register_feature

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    # Bridge unlocked passive-ability modifiers into the Tier 1 modifier resolver.
    _register_modifiers()


manifest = FeatureManifest(
    key="disciplines",
    name="Disciplines & Abilities",
    register_fn=_wire,
)

register_feature(manifest)
