"""Interaction-ability dialogue unlock example (Sprint 74.7, flavor C).

Proves the pure-data path: a `world.yaml` dialogue choice gated on
`actor_has_flag:ability.<id>` (set by training a skill-tree node) appears only
once the flag is held — using the already-shipped dialogue filter, no engine code.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lorecraft.features.npc.dialogue import _visible_choices_for_flags
from lorecraft.features.disciplines.abilities import ability_flag

_ABILITY = "silver_tongue"
_TREE_ID = "innkeeper_dialogue"


def _greeting_node() -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    data = yaml.safe_load((repo_root / "world_content" / "world.yaml").read_text())
    tree = next(t for t in data["dialogue_trees"] if t["id"] == _TREE_ID)
    return tree["nodes"]["greeting"]


def _silver_tongue_labels(node: dict, flags: dict[str, bool]) -> list[str]:
    return [
        str(c.get("label", ""))
        for c in _visible_choices_for_flags(node, flags)
        if ability_flag(_ABILITY) in c.get("actor_has_flag", [])
    ]


def test_world_content_node_is_gated_on_the_ability_flag() -> None:
    node = _greeting_node()
    gated = [
        c
        for c in node["choices"]
        if ability_flag(_ABILITY) in c.get("actor_has_flag", [])
    ]
    # The example option exists and is gated on ability.silver_tongue.
    assert len(gated) == 1


def test_option_hidden_without_ability_flag() -> None:
    node = _greeting_node()
    assert _silver_tongue_labels(node, {}) == []


def test_option_visible_with_ability_flag() -> None:
    node = _greeting_node()
    visible = _silver_tongue_labels(node, {ability_flag(_ABILITY): True})
    assert len(visible) == 1
