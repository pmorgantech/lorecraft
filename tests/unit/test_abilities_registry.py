"""Ability definition loading, validation, and Tier 1 projection (Sprint 78.2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lorecraft.features.disciplines.abilities import (
    AbilityRegistry,
    ability_flag,
    validate_ability_document,
)


def _ability(ability_id: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": ability_id,
        "name": ability_id.title(),
        "discipline": "survival",
        "cost": 1,
        "unlock": {},
    }
    base.update(overrides)
    return base


def test_loads_and_injects_ability_flag() -> None:
    doc = validate_ability_document(
        {
            "version": 1,
            "abilities": [
                _ability("forage"),
                _ability(
                    "sharp_eyes",
                    discipline="subterfuge",
                    cost=2,
                    prerequisites=["forage"],
                ),
            ],
        }
    )
    assert [a.id for a in doc.abilities] == ["forage", "sharp_eyes"]
    assert ability_flag("forage") in doc.abilities[0].unlock.flags


def test_to_ability_def_projects_usage_and_structure() -> None:
    doc = validate_ability_document(
        {
            "abilities": [
                _ability(
                    "forage",
                    ability_type="active",
                    activation_type="instant",
                    required_discipline_rank=3,
                    required_level=5,
                    usage={
                        "terrain": ["outdoor"],
                        "character_states": ["rested"],
                        "resource": {"type": "stamina", "cost": 2},
                        "cooldown_seconds": 30,
                    },
                    proficiency_model="success_only",
                )
            ]
        }
    )
    ability_def = doc.abilities[0].to_ability_def()
    assert ability_def.id == "forage"
    assert ability_def.discipline_id == "survival"
    assert ability_def.required_discipline_rank == 3
    assert ability_def.required_level == 5
    assert ability_def.usage.terrain == ("outdoor",)
    assert ability_def.usage.character_states == ("rested",)
    assert ability_def.usage.resource is not None
    assert ability_def.usage.resource.type == "stamina"
    assert ability_def.usage.resource.cost == 2
    assert ability_def.usage.cooldown_seconds == 30


def test_registry_round_trip_and_for_discipline() -> None:
    doc = validate_ability_document(
        {
            "abilities": [
                _ability("forage", discipline="survival"),
                _ability("pick_locks", discipline="subterfuge", cost=2),
            ]
        }
    )
    registry = AbilityRegistry()
    registry.load_document(doc)
    assert "forage" in registry
    assert {a.id for a in registry.for_discipline("subterfuge")} == {"pick_locks"}
    assert {a.id for a in registry.all()} == {"forage", "pick_locks"}


def test_unknown_prerequisite_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_ability_document(
            {"abilities": [_ability("sharp_eyes", prerequisites=["missing"])]}
        )


def test_prerequisite_cycle_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_ability_document(
            {
                "abilities": [
                    _ability("a", prerequisites=["b"]),
                    _ability("b", prerequisites=["a"]),
                ]
            }
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"cost": 0},
        {"tier": 0},
        {"proficiency_model": "accuracy_and_damage"},
        {"required_discipline_rank": -1},
        {"id": ""},
    ],
)
def test_invalid_ability_fields_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validate_ability_document({"abilities": [_ability("bad", **overrides)]})
