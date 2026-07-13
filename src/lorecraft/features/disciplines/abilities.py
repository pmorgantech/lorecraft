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
  `world_content/abilities.yaml`. Generalizes the old `SkillTreeNode`, adding the
  discipline/usage fields the Tier 1 `AbilityDef` mechanism needs; `to_ability_def`
  projects it down to that opinion-free value object (display fields stay Tier 2).

Definitions are Tier 2 policy (which disciplines/abilities cost what, grant what);
this module holds only the schema + registries, no hardcoded ids. Earned state
lives on `PlayerStats` (`discipline_ranks` + `unlocked_nodes`).
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from lorecraft.engine.game.abilities import (
    AbilityDef,
    ResourceCost,
    UsageRequirements,
)
from lorecraft.engine.game.modifiers import ModifierKind

DISCIPLINE_SCHEMA_VERSION = 1
ABILITY_SCHEMA_VERSION = 1

# Proficiency-growth defaults, lifted verbatim from the old
# `features/skills/service.py` module constants (`IMPROVE_CHANCE`/`MAX_LEVEL`).
# A discipline may override either in YAML; they are the values fed to the Tier 1
# `resolve_proficiency(improve_chance=…, max_rank=…)` mechanism per use.
DEFAULT_IMPROVE_CHANCE = 0.1
DEFAULT_MAX_RANK = 100

ABILITY_FLAG_PREFIX = "ability."

# Closed enum (§5.6): binary owned/not-owned; feeds a pass/fail skill_check roll;
# also scales an effect's magnitude (reserved, no v1 content). `ability_type` and
# `activation_type` are deliberately *not* enums (§5.5) — open strings so combat
# can add `stance`/`spell`/… later as content, not an engine change.
PROFICIENCY_MODELS = frozenset({"none", "success_only", "success_and_magnitude"})


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


# --- Ability schema (generalizes the old SkillTreeNode, §5.2) -----------------


class AbilityModifier(BaseModel):
    """One always-on modifier a passive ability contributes.

    Maps directly onto the Tier 1 `engine.game.modifiers.Modifier`. `mult`
    amounts are factors (1.1 = +10%), never fractions to add. `key` is an
    arbitrary resolver-namespace string (e.g. `skill.perception`, `price.buy`,
    `carry_capacity`) — not tied to any deleted registry (§6.1, Option A).
    """

    key: str
    kind: ModifierKind = "add"
    amount: float

    @field_validator("key")
    @classmethod
    def _key_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("modifier.key must be non-empty")
        return value

    @field_validator("amount")
    @classmethod
    def _amount_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("modifier.amount must be finite")
        return value

    @model_validator(mode="after")
    def _mult_positive(self) -> AbilityModifier:
        if self.kind == "mult" and self.amount <= 0:
            raise ValueError("modifier.amount must be > 0 for kind=mult")
        return self


class AbilityUnlock(BaseModel):
    """What an ability grants: its `ability.<id>` flag always, plus an optional
    passive modifier and an optional documentation-only verb marker.

    `flags` always carries the ability's `ability.<id>` flag — injected on the
    owning ability if the author omits it — so builders never repeat it.
    `enables_verb` names the verb an active ability unlocks; it is not executable
    (the verb is code, gated on the flag).
    """

    flags: list[str] = Field(default_factory=list)
    modifier: AbilityModifier | None = None
    enables_verb: str | None = None


class ResourceSpec(BaseModel):
    """A resource an ability spends to be performed (§5.2 `usage.resource`)."""

    type: str
    cost: float = 0.0

    @field_validator("type")
    @classmethod
    def _type_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("usage.resource.type must be non-empty")
        return value

    @field_validator("cost")
    @classmethod
    def _cost_non_negative(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("usage.resource.cost must be finite and >= 0")
        return value


class UsageSpec(BaseModel):
    """What must hold for an ability to be *performed* (§5.2 `usage:` block).

    Projects onto the Tier 1 `UsageRequirements`. All fields default to "no
    requirement", so an omitted `usage:` block means "always performable".
    """

    character_states: list[str] = Field(default_factory=list)
    target_states: list[str] = Field(default_factory=list)
    terrain: list[str] = Field(default_factory=list)
    resource: ResourceSpec | None = None
    cooldown_seconds: float = 0.0

    @field_validator("cooldown_seconds")
    @classmethod
    def _cooldown_non_negative(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("usage.cooldown_seconds must be finite and >= 0")
        return value


class AbilityRecord(BaseModel):
    """One ability (§5.2) — content plus the projection to a Tier 1 `AbilityDef`.

    Holds Tier-2-only display fields (`name`/`description`/`flavor`) alongside the
    structural fields the mechanism needs. `ability_type`/`activation_type` are
    open strings (§5.5). `proficiency_model` is the closed §5.6 enum.
    """

    id: str
    name: str
    description: str = ""
    flavor: str = ""
    discipline: str
    branch: str | None = None
    tier: int = 1
    ability_type: str = "active"
    activation_type: str = "instant"
    cost: int
    prerequisites: list[str] = Field(default_factory=list)
    required_discipline_rank: int = 0
    required_level: int | None = None
    usage: UsageSpec = Field(default_factory=UsageSpec)
    unlock: AbilityUnlock
    proficiency_model: str = "none"
    mutually_exclusive_group: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("id", "discipline")
    @classmethod
    def _id_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ability id/discipline must be non-empty")
        return value

    @field_validator("cost")
    @classmethod
    def _cost_at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("ability.cost must be >= 1")
        return value

    @field_validator("tier")
    @classmethod
    def _tier_at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("ability.tier must be >= 1")
        return value

    @field_validator("required_discipline_rank")
    @classmethod
    def _rank_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("ability.required_discipline_rank must be >= 0")
        return value

    @field_validator("proficiency_model")
    @classmethod
    def _known_proficiency_model(cls, value: str) -> str:
        if value not in PROFICIENCY_MODELS:
            raise ValueError(
                f"ability.proficiency_model must be one of {sorted(PROFICIENCY_MODELS)}"
            )
        return value

    @model_validator(mode="after")
    def _ensure_ability_flag(self) -> AbilityRecord:
        """Guarantee the ability's `ability.<id>` flag is in the unlock flag set.

        The flag is the mandatory acquisition gate (active/interaction abilities
        read it), so inject it when the author omits it rather than failing —
        keeps YAML terse while preserving the invariant the purchase path relies
        on (ported verbatim from the old SkillTreeNode behaviour).
        """
        flag = ability_flag(self.id)
        if flag not in self.unlock.flags:
            self.unlock.flags = [flag, *self.unlock.flags]
        return self

    def to_ability_def(self) -> AbilityDef:
        """Project onto the opinion-free Tier 1 `AbilityDef` (drops display fields)."""
        resource = (
            ResourceCost(type=self.usage.resource.type, cost=self.usage.resource.cost)
            if self.usage.resource is not None
            else None
        )
        return AbilityDef(
            id=self.id,
            discipline_id=self.discipline,
            tier=self.tier,
            ability_type=self.ability_type,
            activation_type=self.activation_type,
            prerequisites=tuple(self.prerequisites),
            cost=self.cost,
            required_discipline_rank=self.required_discipline_rank,
            required_level=self.required_level,
            usage=UsageRequirements(
                character_states=tuple(self.usage.character_states),
                target_states=tuple(self.usage.target_states),
                terrain=tuple(self.usage.terrain),
                resource=resource,
                cooldown_seconds=self.usage.cooldown_seconds,
            ),
        )


class AbilityDocument(BaseModel):
    version: int = ABILITY_SCHEMA_VERSION
    abilities: list[AbilityRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_graph(self) -> AbilityDocument:
        ids = [a.id for a in self.abilities]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate ability ids: {dupes}")

        known = set(ids)
        for ability in self.abilities:
            for prereq in ability.prerequisites:
                if prereq not in known:
                    raise ValueError(
                        f"ability {ability.id!r} lists unknown prerequisite {prereq!r}"
                    )
                if prereq == ability.id:
                    raise ValueError(
                        f"ability {ability.id!r} lists itself as a prerequisite"
                    )

        cycle = _find_cycle({a.id: a.prerequisites for a in self.abilities})
        if cycle is not None:
            raise ValueError(f"prerequisite cycle: {' -> '.join(cycle)}")
        return self


def _find_cycle(edges: dict[str, list[str]]) -> list[str] | None:
    """Return one prerequisite cycle as an id path, or None if the graph is a DAG.

    `edges[id]` are that ability's prerequisites (its dependencies). A cycle among
    them means no purchase order can ever satisfy the chain.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    color = {node: WHITE for node in edges}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = GREY
        stack.append(node)
        for dep in edges.get(node, ()):
            if color.get(dep) == GREY:
                start = stack.index(dep)
                return [*stack[start:], dep]
            if color.get(dep) == WHITE:
                found = visit(dep)
                if found is not None:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for node in edges:
        if color[node] == WHITE:
            found = visit(node)
            if found is not None:
                return found
    return None


def validate_ability_document(data: object) -> AbilityDocument:
    return AbilityDocument.model_validate(data)


def load_abilities_yaml(path: str | Path) -> AbilityDocument:
    text = Path(path).read_text(encoding="utf-8")
    return validate_ability_document(yaml.safe_load(text) or {})


class AbilityRegistry:
    """In-memory catalogue of ability records (mirrors the old SkillTreeRegistry)."""

    def __init__(self) -> None:
        self._records: dict[str, AbilityRecord] = {}

    def register(self, record: AbilityRecord) -> None:
        self._records[record.id] = record

    def load_document(self, document: AbilityDocument) -> None:
        for record in document.abilities:
            self.register(record)

    def get(self, ability_id: str) -> AbilityRecord | None:
        return self._records.get(ability_id)

    def all(self) -> list[AbilityRecord]:
        return list(self._records.values())

    def for_discipline(self, discipline_id: str) -> list[AbilityRecord]:
        return [r for r in self._records.values() if r.discipline == discipline_id]

    def clear(self) -> None:
        self._records.clear()

    def __contains__(self, ability_id: str) -> bool:
        return ability_id in self._records


_ability_registry = AbilityRegistry()


def get_ability_registry() -> AbilityRegistry:
    return _ability_registry
