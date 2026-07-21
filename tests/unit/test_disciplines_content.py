"""World-content validation for disciplines.yaml + abilities.yaml (Sprint 78.4).

Loads the *real* authored content (not fixtures) to prove the pre-78 skill-tree
migration is lossless and internally consistent — every ability references a real
discipline, and the 7 legacy nodes survive with their ids/costs/unlocks intact.
`harvest` was added later (gap #2 harvest-verb work) as a legitimate 8th ability
under the `survival` discipline; `_EXPECTED_ABILITY_DISCIPLINE` tracks it too.
"""

from __future__ import annotations

from lorecraft.features.disciplines.abilities import (
    load_abilities_yaml,
    load_disciplines_yaml,
)

_DISCIPLINES = "world_content/disciplines.yaml"
_ABILITIES = "world_content/abilities.yaml"

# The full §7 seed set.
_EXPECTED_DISCIPLINES = {"survival", "subterfuge", "commerce", "rhetoric", "fortitude"}
# The 7 migrated legacy nodes plus `harvest` (added later), mapped to their
# §7 discipline.
_EXPECTED_ABILITY_DISCIPLINE = {
    "forage": "survival",
    "harvest": "survival",
    "keen_senses": "subterfuge",
    "pick_locks": "subterfuge",
    "mule": "fortitude",
    "sharp_eyes": "subterfuge",
    "haggler": "commerce",
    "silver_tongue": "rhetoric",
}


def test_disciplines_content_is_the_five_seed_disciplines() -> None:
    doc = load_disciplines_yaml(_DISCIPLINES)
    assert {d.id for d in doc.disciplines} == _EXPECTED_DISCIPLINES


def test_abilities_content_is_the_seven_migrated_nodes_plus_harvest() -> None:
    doc = load_abilities_yaml(_ABILITIES)
    assert {a.id for a in doc.abilities} == set(_EXPECTED_ABILITY_DISCIPLINE)


def test_every_ability_references_a_real_discipline() -> None:
    disciplines = {d.id for d in load_disciplines_yaml(_DISCIPLINES).disciplines}
    for ability in load_abilities_yaml(_ABILITIES).abilities:
        assert ability.discipline in disciplines, ability.id
        assert _EXPECTED_ABILITY_DISCIPLINE[ability.id] == ability.discipline


def test_forage_usage_terrain_replaces_the_hardcoded_indoor_check() -> None:
    forage = next(
        a for a in load_abilities_yaml(_ABILITIES).abilities if a.id == "forage"
    )
    assert forage.to_ability_def().usage.terrain == ("outdoor",)


def test_sharp_eyes_keeps_the_skill_perception_modifier_key() -> None:
    # Option A: no remap — the modifier still resolves under `skill.perception`.
    sharp_eyes = next(
        a for a in load_abilities_yaml(_ABILITIES).abilities if a.id == "sharp_eyes"
    )
    assert sharp_eyes.unlock.modifier is not None
    assert sharp_eyes.unlock.modifier.key == "skill.perception"
    assert sharp_eyes.prerequisites == ["keen_senses"]


def test_migrated_costs_match_the_legacy_skill_tree() -> None:
    by_id = {a.id: a for a in load_abilities_yaml(_ABILITIES).abilities}
    assert by_id["forage"].cost == 1
    assert by_id["pick_locks"].cost == 2
    assert by_id["sharp_eyes"].cost == 2
    assert by_id["haggler"].cost == 2
