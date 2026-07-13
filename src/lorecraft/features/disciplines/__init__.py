"""Disciplines feature — the Tier 2 policy layer for the Discipline/Ability system.

This package is the opinionated, data-driven home for *what* disciplines and
abilities exist, what they cost, and what they grant — feeding the opinion-free
Tier 1 mechanism in `engine.game.abilities`. It ultimately replaces both
`features/skills/` (the flat skill catalog) and
`features/progression/skill_tree.py`'s node shape with one coherent model — see
`docs/discipline_ability_system.md`.

Sprint 77 (Tier 1) ships only this skeleton: a manifest so the package is
auto-discovered by `discover_features()` and a placement for the registry/service
work. The registries (`DisciplineRegistry`/`AbilityRegistry`), the
`world_content/disciplines.yaml` + `abilities.yaml` loaders, the `PlayerStats`
migration, and the `train`/`learn` command rework all land in Sprint 78 (Phases
B.2–F). Until then this is a passive manifest with no `register_fn` — it wires
nothing onto the shared registries yet. It imports only `engine.*` (never a web
host), per the tier boundary.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="disciplines", name="Disciplines & Abilities")

register_feature(manifest)
