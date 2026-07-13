"""Discipline/Ability policy service (Sprint 78 fills this in).

Sprint 77 ships only the placement: the Tier 1 mechanism
(`engine.game.abilities`) is done and unit-tested, but the Tier 2 service that
drives it — loading `DisciplineDef`/`AbilityDef` records from
`world_content/disciplines.yaml` + `abilities.yaml`, tracking per-player
discipline ranks and owned abilities, and calling `check_acquisition` /
`check_usage` / `resolve_proficiency` with config-supplied dials — is deferred to
Sprint 78 (Phases B.2–F). See `docs/discipline_ability_system.md`.

Intentionally empty of behaviour for now so the module path exists for Sprint 78
to build on without a churny move. Importing it must stay side-effect-free and
touch only `engine.*` (never a web host), per the tier boundary.
"""

from __future__ import annotations
