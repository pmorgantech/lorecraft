"""Data-authored combat action definitions.

Combat actions are Tier 2 policy: content decides which action ids exist, how
long they take, what broad target range they use, and which registered resolver
handles them. The service still owns the narrow Python implementation of those
resolvers.
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from lorecraft.features.combat.policy import (
    ACTION_BASIC_ATTACK,
    ACTION_DEFEND,
    ACTION_FLEE,
    ACTION_RANGE_ENGAGED,
    ACTION_RANGE_RANGED,
    ACTION_RANGE_SELF,
    ACTION_RANGED_ATTACK,
)

COMBAT_ACTION_SCHEMA_VERSION = 1

ACTION_CHANNEL_PRIMARY = "primary"

CALCULATOR_OPPOSED_ATTACK = "opposed_attack"
CALCULATOR_SELF = "self"

RESOLVER_OPPOSED_ATTACK = "opposed_attack"
RESOLVER_DEFEND = "defend"
RESOLVER_FLEE = "flee"

VALID_ACTION_RANGES = frozenset(
    {ACTION_RANGE_SELF, ACTION_RANGE_ENGAGED, ACTION_RANGE_RANGED}
)


class CombatComponentDef(BaseModel):
    key: str
    description: str = ""

    @field_validator("key")
    @classmethod
    def _key_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("combat component key must be non-empty")
        return value


class CombatActionTiming(BaseModel):
    windup: float = Field(ge=0)
    recovery: float = Field(ge=0)

    @field_validator("windup", "recovery")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("combat action timing must be finite")
        return value


class CombatActionDef(BaseModel):
    id: str
    channel: str = ACTION_CHANNEL_PRIMARY
    ruleset_id: str = "default"
    action_range: str
    calculator: str = CALCULATOR_OPPOSED_ATTACK
    resolver: str = RESOLVER_OPPOSED_ATTACK
    resolver_version: str = "opposed-v1"
    timing: CombatActionTiming
    stamina_delta: float | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator(
        "id", "channel", "ruleset_id", "calculator", "resolver", "resolver_version"
    )
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "combat action id/channel/ruleset/calculator/resolver/version must be non-empty"
            )
        return value

    @field_validator("action_range")
    @classmethod
    def _known_action_range(cls, value: str) -> str:
        if value not in VALID_ACTION_RANGES:
            raise ValueError(f"unknown combat action range: {value!r}")
        return value

    @field_validator("stamina_delta")
    @classmethod
    def _stamina_delta_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("combat action stamina_delta must be finite")
        return value


class CombatActionsDocument(BaseModel):
    version: int = COMBAT_ACTION_SCHEMA_VERSION
    actions: list[CombatActionDef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> CombatActionsDocument:
        ids = [action.id for action in self.actions]
        dupes = sorted({action_id for action_id in ids if ids.count(action_id) > 1})
        if dupes:
            raise ValueError(f"duplicate combat action ids: {dupes}")
        return self


def validate_combat_actions_document(data: object) -> CombatActionsDocument:
    return CombatActionsDocument.model_validate(data)


def load_combat_actions_yaml(path: str | Path) -> CombatActionsDocument:
    text = Path(path).read_text(encoding="utf-8")
    return validate_combat_actions_document(yaml.safe_load(text) or {})


class CombatComponentRegistry:
    """Registered calculator/resolver keys that action YAML may reference."""

    def __init__(self) -> None:
        self._calculators: dict[str, CombatComponentDef] = {}
        self._resolvers: dict[str, CombatComponentDef] = {}

    def register_calculator(self, component: CombatComponentDef) -> None:
        self._calculators[component.key] = component

    def register_resolver(self, component: CombatComponentDef) -> None:
        self._resolvers[component.key] = component

    def has_calculator(self, key: str) -> bool:
        return key in self._calculators

    def has_resolver(self, key: str) -> bool:
        return key in self._resolvers

    def calculators(self) -> list[CombatComponentDef]:
        return list(self._calculators.values())

    def resolvers(self) -> list[CombatComponentDef]:
        return list(self._resolvers.values())

    def clear(self) -> None:
        self._calculators.clear()
        self._resolvers.clear()


class CombatActionRegistry:
    def __init__(self, components: CombatComponentRegistry | None = None) -> None:
        self._actions: dict[str, CombatActionDef] = {}
        self._components = components or get_component_registry()

    def register(self, action: CombatActionDef) -> None:
        if not self._components.has_calculator(action.calculator):
            raise ValueError(
                f"combat action {action.id!r} references unknown calculator "
                f"{action.calculator!r}"
            )
        if not self._components.has_resolver(action.resolver):
            raise ValueError(
                f"combat action {action.id!r} references unknown resolver "
                f"{action.resolver!r}"
            )
        self._actions[action.id] = action

    def load_document(self, document: CombatActionsDocument) -> None:
        for action in document.actions:
            self.register(action)

    def get(self, action_id: str) -> CombatActionDef | None:
        return self._actions.get(action_id)

    def all(self) -> list[CombatActionDef]:
        return list(self._actions.values())

    def clear(self) -> None:
        self._actions.clear()


_component_registry = CombatComponentRegistry()
_action_registry = CombatActionRegistry(_component_registry)


def get_component_registry() -> CombatComponentRegistry:
    return _component_registry


def get_action_registry() -> CombatActionRegistry:
    return _action_registry


def register_standard_combat_components(
    registry: CombatComponentRegistry | None = None,
) -> None:
    target = registry or get_component_registry()
    target.register_calculator(
        CombatComponentDef(
            key=CALCULATOR_OPPOSED_ATTACK,
            description="Opposed attack and defense score calculation.",
        )
    )
    target.register_calculator(
        CombatComponentDef(
            key=CALCULATOR_SELF,
            description="Self-targeted action with no opposed target roll.",
        )
    )
    target.register_resolver(
        CombatComponentDef(
            key=RESOLVER_OPPOSED_ATTACK,
            description="Resolve a targeted physical attack.",
        )
    )
    target.register_resolver(
        CombatComponentDef(
            key=RESOLVER_DEFEND,
            description="Resolve a self-targeted defensive brace.",
        )
    )
    target.register_resolver(
        CombatComponentDef(
            key=RESOLVER_FLEE,
            description="Resolve a self-targeted escape attempt.",
        )
    )


def default_combat_actions_document() -> CombatActionsDocument:
    return CombatActionsDocument(
        actions=[
            CombatActionDef(
                id=ACTION_BASIC_ATTACK,
                ruleset_id="core",
                action_range=ACTION_RANGE_ENGAGED,
                calculator=CALCULATOR_OPPOSED_ATTACK,
                resolver=RESOLVER_OPPOSED_ATTACK,
                resolver_version="opposed-v1",
                timing=CombatActionTiming(windup=0.25, recovery=2.0),
                stamina_delta=-6.0,
                tags=["melee", "physical"],
            ),
            CombatActionDef(
                id=ACTION_RANGED_ATTACK,
                ruleset_id="core",
                action_range=ACTION_RANGE_RANGED,
                calculator=CALCULATOR_OPPOSED_ATTACK,
                resolver=RESOLVER_OPPOSED_ATTACK,
                resolver_version="opposed-v1",
                timing=CombatActionTiming(windup=0.35, recovery=2.2),
                stamina_delta=-6.0,
                tags=["ranged", "physical"],
            ),
            CombatActionDef(
                id=ACTION_DEFEND,
                ruleset_id="core",
                action_range=ACTION_RANGE_SELF,
                calculator=CALCULATOR_SELF,
                resolver=RESOLVER_DEFEND,
                resolver_version="defend-v1",
                timing=CombatActionTiming(windup=0.0, recovery=1.2),
                stamina_delta=-2.0,
                tags=["defense"],
            ),
            CombatActionDef(
                id=ACTION_FLEE,
                ruleset_id="core",
                action_range=ACTION_RANGE_SELF,
                calculator=CALCULATOR_SELF,
                resolver=RESOLVER_FLEE,
                resolver_version="flee-v1",
                timing=CombatActionTiming(windup=0.35, recovery=2.5),
                tags=["escape"],
            ),
        ]
    )


def register_builtin_combat_actions(
    registry: CombatActionRegistry | None = None,
) -> None:
    register_standard_combat_components()
    target = registry or get_action_registry()
    target.clear()
    target.load_document(default_combat_actions_document())


register_builtin_combat_actions()
