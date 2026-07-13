"""Discipline & ability *content* schema, loaders, and registries (Sprint 78).

This module is the Tier 2 policy home for *what* disciplines and abilities exist —
the renamed/extended successor to `features/progression/skill_tree.py` (§6.3 of
`docs/discipline_ability_system.md`). It defines two content records:

- **`DisciplineDef`** — a themed body of practice (Survival, Subterfuge, …),
  authored in `world_content/disciplines.yaml`. Carries the two proficiency-growth
  dials (`improve_chance`/`max_rank`) that the Tier 1 `resolve_proficiency`
  mechanism takes as parameters — lifted out of the old `SkillService` module
  constants (§2) so they are per-discipline content, not engine policy.
- **`AbilityRecord`** — one concrete ability within a discipline, authored in
  `world_content/abilities.yaml` (added in 78.2). Generalizes the old
  `SkillTreeNode`, adding the discipline/usage fields the Tier 1 `AbilityDef`
  mechanism needs.

Definitions are Tier 2 policy (which disciplines/abilities cost what, grant what);
this module holds only the schema + registries, no hardcoded ids. Earned state
lives on `PlayerStats` (`discipline_ranks` + `unlocked_nodes`).
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from lorecraft.engine.game.modifiers import ModifierKind

DISCIPLINE_SCHEMA_VERSION = 1

# Proficiency-growth defaults, lifted verbatim from the old
# `features/skills/service.py` module constants (`IMPROVE_CHANCE`/`MAX_LEVEL`).
# A discipline may override either in YAML; they are the values fed to the Tier 1
# `resolve_proficiency(improve_chance=…, max_rank=…)` mechanism per use.
DEFAULT_IMPROVE_CHANCE = 0.1
DEFAULT_MAX_RANK = 100

ABILITY_FLAG_PREFIX = "ability."


def ability_flag(ability_id: str) -> str:
    """The canonical player flag an ability purchase sets (`ability.<id>`).

    This is the load-bearing flag active-verb and dialogue gating reads via
    `actor_has_flag:ability.<id>` — every ability grants it (see 74-OI-2), the
    same convention the old skill tree used.
    """
    return f"{ABILITY_FLAG_PREFIX}{ability_id}"


# --- Discipline schema --------------------------------------------------------


class DisciplineDef(BaseModel):
    """One discipline (§5.1) — a themed body of practice a player specializes in.

    `governing_stat` mirrors the old `SkillDef.governing_stat`. `improve_chance`
    and `max_rank` are the proficiency-growth dials the Tier 1 mechanism consumes
    as parameters; defaulting them keeps terse YAML while allowing a per-discipline
    override (a fast-learning vs. deep-mastery discipline).
    """

    id: str
    name: str
    description: str = ""
    governing_stat: str
    improve_chance: float = DEFAULT_IMPROVE_CHANCE
    max_rank: int = DEFAULT_MAX_RANK

    @field_validator("id", "governing_stat")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("discipline id/governing_stat must be non-empty")
        return value

    @field_validator("improve_chance")
    @classmethod
    def _improve_chance_ratio(cls, value: float) -> float:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("discipline.improve_chance must be in [0, 1]")
        return value

    @field_validator("max_rank")
    @classmethod
    def _max_rank_at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("discipline.max_rank must be >= 1")
        return value


class DisciplineDocument(BaseModel):
    version: int = DISCIPLINE_SCHEMA_VERSION
    disciplines: list[DisciplineDef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> DisciplineDocument:
        ids = [d.id for d in self.disciplines]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate discipline ids: {dupes}")
        return self


def validate_discipline_document(data: object) -> DisciplineDocument:
    return DisciplineDocument.model_validate(data)


def load_disciplines_yaml(path: str | Path) -> DisciplineDocument:
    text = Path(path).read_text(encoding="utf-8")
    return validate_discipline_document(yaml.safe_load(text) or {})


class DisciplineRegistry:
    """In-memory catalogue of discipline definitions (mirrors `MarkRegistry`)."""

    def __init__(self) -> None:
        self._defs: dict[str, DisciplineDef] = {}

    def register(self, discipline: DisciplineDef) -> None:
        self._defs[discipline.id] = discipline

    def load_document(self, document: DisciplineDocument) -> None:
        for discipline in document.disciplines:
            self.register(discipline)

    def get(self, discipline_id: str) -> DisciplineDef | None:
        return self._defs.get(discipline_id)

    def all(self) -> list[DisciplineDef]:
        return list(self._defs.values())

    def clear(self) -> None:
        self._defs.clear()

    def __contains__(self, discipline_id: str) -> bool:
        return discipline_id in self._defs


_discipline_registry = DisciplineRegistry()


def get_discipline_registry() -> DisciplineRegistry:
    return _discipline_registry


# `ModifierKind` is re-exported for the ability-modifier schema added in 78.2.
__all__ = [
    "ABILITY_FLAG_PREFIX",
    "DEFAULT_IMPROVE_CHANCE",
    "DEFAULT_MAX_RANK",
    "DISCIPLINE_SCHEMA_VERSION",
    "DisciplineDef",
    "DisciplineDocument",
    "DisciplineRegistry",
    "ModifierKind",
    "ability_flag",
    "get_discipline_registry",
    "load_disciplines_yaml",
    "validate_discipline_document",
]
