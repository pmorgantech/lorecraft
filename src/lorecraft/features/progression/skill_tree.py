"""Skill-tree definitions: schema, loader, registry, content-lint (Sprint 74.1).

The skill tree is *content* — like rooms/items/marks — authored in
`world_content/skill_tree.yaml` and loaded into an in-memory registry at startup
(the marks-def pattern). A node is bought with skill points and unlocks an
*ability*, converging on the `ability.<id>` player flag: active verbs gate on it
(`actor_has_flag`), passive nodes additionally register a `modifier`, and
interaction/dialogue nodes carry only the flag(s).

Definition source is Tier 2 policy (which nodes cost what, grant what); this
module holds only the schema + registry, no hardcoded node ids. Earned state
lives elsewhere (PlayerStats.unlocked_nodes + the flag) — see 74.2.
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from lorecraft.engine.game.modifiers import ModifierKind

SKILL_TREE_SCHEMA_VERSION = 1

ABILITY_FLAG_PREFIX = "ability."


def ability_flag(node_id: str) -> str:
    """The canonical player flag a node purchase sets (`ability.<node_id>`).

    This is the load-bearing flag active-verb and dialogue gating reads via
    `actor_has_flag:ability.<id>` — every node grants it (see 74-OI-2).
    """
    return f"{ABILITY_FLAG_PREFIX}{node_id}"


class NodeModifier(BaseModel):
    """One always-on modifier a passive (flavor B) node contributes.

    Maps directly onto the Tier 1 `engine.game.modifiers.Modifier`. `mult`
    amounts are factors (1.1 = +10%), never fractions to add.
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
    def _mult_positive(self) -> NodeModifier:
        if self.kind == "mult" and self.amount <= 0:
            raise ValueError("modifier.amount must be > 0 for kind=mult")
        return self


class NodeUnlock(BaseModel):
    """What a node grants: flag(s) always, plus an optional passive modifier and
    an optional documentation-only verb marker.

    `flags` always carries the node's `ability.<id>` flag — it is injected on the
    owning node if the author omits it (see `SkillTreeNode`), so builders never
    have to repeat it. `enables_verb` is a marker string naming the verb an
    active (flavor A) node unlocks; it is not executable — the verb is code,
    gated on the flag.
    """

    flags: list[str] = Field(default_factory=list)
    modifier: NodeModifier | None = None
    enables_verb: str | None = None


class SkillTreeNode(BaseModel):
    id: str
    name: str
    description: str = ""
    cost: int
    prerequisites: list[str] = Field(default_factory=list)
    unlock: NodeUnlock

    @field_validator("id")
    @classmethod
    def _id_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("node.id must be non-empty")
        return value

    @field_validator("cost")
    @classmethod
    def _cost_at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("node.cost must be >= 1")
        return value

    @model_validator(mode="after")
    def _ensure_ability_flag(self) -> SkillTreeNode:
        """Guarantee the node's `ability.<id>` flag is in the unlock flag set.

        The flag is mandatory (flavors A and C gate on it), so inject it when the
        author omits it rather than failing — keeps YAML terse while preserving
        the invariant the purchase path relies on.
        """
        flag = ability_flag(self.id)
        if flag not in self.unlock.flags:
            self.unlock.flags = [flag, *self.unlock.flags]
        return self


class SkillTreeDocument(BaseModel):
    version: int = SKILL_TREE_SCHEMA_VERSION
    nodes: list[SkillTreeNode] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_graph(self) -> SkillTreeDocument:
        ids = [node.id for node in self.nodes]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate node ids: {dupes}")

        known = set(ids)
        for node in self.nodes:
            for prereq in node.prerequisites:
                if prereq not in known:
                    raise ValueError(
                        f"node {node.id!r} lists unknown prerequisite {prereq!r}"
                    )
                if prereq == node.id:
                    raise ValueError(f"node {node.id!r} lists itself as a prerequisite")

        cycle = _find_cycle({n.id: n.prerequisites for n in self.nodes})
        if cycle is not None:
            raise ValueError(f"prerequisite cycle: {' -> '.join(cycle)}")
        return self


def _find_cycle(edges: dict[str, list[str]]) -> list[str] | None:
    """Return one prerequisite cycle as a node-id path, or None if the graph is a DAG.

    `edges[node]` are that node's prerequisites (its dependencies). A cycle among
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


def validate_skill_tree_document(data: object) -> SkillTreeDocument:
    return SkillTreeDocument.model_validate(data)


def load_skill_tree_yaml(path: str | Path) -> SkillTreeDocument:
    text = Path(path).read_text(encoding="utf-8")
    return validate_skill_tree_document(yaml.safe_load(text) or {})


class SkillTreeRegistry:
    """In-memory catalogue of skill-tree nodes (mirrors `MarkRegistry`)."""

    def __init__(self) -> None:
        self._nodes: dict[str, SkillTreeNode] = {}

    def register(self, node: SkillTreeNode) -> None:
        self._nodes[node.id] = node

    def load_document(self, document: SkillTreeDocument) -> None:
        for node in document.nodes:
            self.register(node)

    def get(self, node_id: str) -> SkillTreeNode | None:
        return self._nodes.get(node_id)

    def all(self) -> list[SkillTreeNode]:
        return list(self._nodes.values())

    def clear(self) -> None:
        self._nodes.clear()

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._nodes


_registry = SkillTreeRegistry()


def get_registry() -> SkillTreeRegistry:
    return _registry
