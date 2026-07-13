"""Skill-tree definition loading + validation (Sprint 74.1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lorecraft.features.progression.skill_tree import (
    SkillTreeRegistry,
    ability_flag,
    validate_skill_tree_document,
)


def _node(node_id: str, *, cost: int = 1, prerequisites: list[str] | None = None):
    return {
        "id": node_id,
        "name": node_id.title(),
        "cost": cost,
        "prerequisites": prerequisites or [],
        "unlock": {},
    }


def test_loads_valid_document_and_injects_ability_flag() -> None:
    doc = validate_skill_tree_document(
        {
            "version": 1,
            "nodes": [
                _node("forage"),
                _node("sharp_eyes", cost=2, prerequisites=["forage"]),
            ],
        }
    )
    assert [n.id for n in doc.nodes] == ["forage", "sharp_eyes"]
    # ability.<id> flag is injected even though the YAML omitted it.
    assert ability_flag("forage") in doc.nodes[0].unlock.flags


def test_author_supplied_ability_flag_is_not_duplicated() -> None:
    node = _node("silver_tongue")
    node["unlock"] = {"flags": [ability_flag("silver_tongue")]}
    doc = validate_skill_tree_document({"nodes": [node]})
    assert doc.nodes[0].unlock.flags.count(ability_flag("silver_tongue")) == 1


def test_modifier_node_round_trips() -> None:
    node = _node("mule")
    node["unlock"] = {
        "modifier": {"key": "carry_capacity", "kind": "add", "amount": 20}
    }
    doc = validate_skill_tree_document({"nodes": [node]})
    modifier = doc.nodes[0].unlock.modifier
    assert modifier is not None
    assert modifier.key == "carry_capacity"
    assert modifier.amount == 20


def test_cost_below_one_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cost must be >= 1"):
        validate_skill_tree_document({"nodes": [_node("bad", cost=0)]})


def test_missing_prerequisite_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown prerequisite"):
        validate_skill_tree_document(
            {"nodes": [_node("child", prerequisites=["ghost"])]}
        )


def test_self_prerequisite_is_rejected() -> None:
    with pytest.raises(ValidationError, match="itself as a prerequisite"):
        validate_skill_tree_document(
            {"nodes": [_node("loner", prerequisites=["loner"])]}
        )


def test_prerequisite_cycle_is_rejected() -> None:
    with pytest.raises(ValidationError, match="prerequisite cycle"):
        validate_skill_tree_document(
            {
                "nodes": [
                    _node("a", prerequisites=["b"]),
                    _node("b", prerequisites=["c"]),
                    _node("c", prerequisites=["a"]),
                ]
            }
        )


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate node ids"):
        validate_skill_tree_document({"nodes": [_node("dup"), _node("dup")]})


def test_mult_modifier_must_be_positive() -> None:
    node = _node("bad_mult")
    node["unlock"] = {"modifier": {"key": "price.buy", "kind": "mult", "amount": 0}}
    with pytest.raises(ValidationError, match="must be > 0 for kind=mult"):
        validate_skill_tree_document({"nodes": [node]})


def test_registry_load_and_lookup() -> None:
    doc = validate_skill_tree_document({"nodes": [_node("forage")]})
    registry = SkillTreeRegistry()
    registry.load_document(doc)
    assert "forage" in registry
    assert registry.get("forage") is not None
    assert registry.get("missing") is None
    assert len(registry.all()) == 1
    registry.clear()
    assert registry.all() == []


def test_shipped_world_content_skill_tree_is_valid() -> None:
    """The authored world_content/skill_tree.yaml loads and validates."""
    from pathlib import Path

    from lorecraft.features.progression.skill_tree import load_skill_tree_yaml

    repo_root = Path(__file__).resolve().parents[2]
    doc = load_skill_tree_yaml(repo_root / "world_content" / "skill_tree.yaml")
    ids = {n.id for n in doc.nodes}
    # The three reference verb-unlock nodes must be present (74-OI-3).
    assert {"forage", "keen_senses", "pick_locks"} <= ids
