"""A0.4 — the fail-closed author-time validator for when:/do: blocks.

Validates names/kinds/param-shapes against a catalog. Uses a hand-built :class:`Vocabulary`
so the tests don't depend on which real registrations happen to exist yet (A2/A5 add many of
the names in the design's examples). See ``docs/scripting_engine_design.md`` §8.5.
"""

from __future__ import annotations

from lorecraft.engine.scripting.validator import (
    validate_conditions,
    validate_effects,
)
from lorecraft.engine.scripting.vocabulary import (
    CapabilitySig,
    ParamSpec,
    Subject,
    VocabEntry,
    Vocabulary,
    VocabKind,
)
from lorecraft.types import JsonValue


def _vocab() -> Vocabulary:
    v = Vocabulary()
    v.register(
        VocabEntry(
            "actor_has_flag",
            VocabKind.CONDITION,
            Subject.ACTOR,
            "flags",
            "Actor has a flag.",
            CapabilitySig(Subject.ACTOR, "flags", "<flag>", "has"),
            params=(ParamSpec("flag", "flag"),),
        )
    )
    v.register(
        VocabEntry(
            "actor_reputation_at_least",
            VocabKind.CONDITION,
            Subject.ACTOR,
            "social",
            "Actor reputation >= value.",
            CapabilitySig(Subject.ACTOR, "reputation", "standing", "at_least"),
            params=(ParamSpec("faction", "faction"), ParamSpec("value", "int")),
        )
    )
    v.register(
        VocabEntry(
            "give_item",
            VocabKind.EFFECT,
            Subject.ACTOR,
            "inventory",
            "Give an item.",
            CapabilitySig(Subject.ACTOR, "inventory", "item", "give"),
            params=(ParamSpec("item_id", "item_id"),),
        )
    )
    v.register(
        VocabEntry(
            "apply_effect",
            VocabKind.EFFECT,
            Subject.TARGET,
            "effects",
            "Apply a timed effect.",
            CapabilitySig(Subject.TARGET, "effects", "active", "apply"),
            params=(
                ParamSpec("target", "subject"),
                ParamSpec("effect", "effect_id"),
                ParamSpec("ticks", "int"),
            ),
        )
    )
    return v


def test_known_condition_and_effect_pass() -> None:
    v = _vocab()
    assert validate_conditions({"actor_has_flag": "vip"}, v) == []
    assert validate_effects([{"give_item": "brass_key"}], v) == []


def test_unknown_condition_is_flagged() -> None:
    issues = validate_conditions({"player_has_mark": "poacher"}, _vocab())
    assert len(issues) == 1
    assert "unknown condition 'player_has_mark'" in issues[0].message


def test_unknown_effect_is_flagged() -> None:
    issues = validate_effects([{"narrate_room": "hi"}], _vocab())
    assert len(issues) == 1
    assert "unknown effect 'narrate_room'" in issues[0].message


def test_wrong_kind_is_flagged() -> None:
    # give_item is an effect; using it in a when: block is a kind error.
    issues = validate_conditions({"give_item": "brass_key"}, _vocab())
    assert len(issues) == 1
    assert "is a effect, not a condition" in issues[0].message


def test_multi_param_effect_missing_key_is_flagged() -> None:
    issues = validate_effects([{"apply_effect": {"target": "actor"}}], _vocab())
    assert len(issues) == 1
    assert "missing required param(s)" in issues[0].message
    assert "effect" in issues[0].message and "ticks" in issues[0].message


def test_multi_param_effect_wrong_shape_is_flagged() -> None:
    issues = validate_effects([{"apply_effect": "watched"}], _vocab())
    assert len(issues) == 1
    assert "expects a map" in issues[0].message


def test_multi_param_effect_complete_passes() -> None:
    block: JsonValue = [
        {"apply_effect": {"target": "actor", "effect": "watched", "ticks": 20}}
    ]
    assert validate_effects(block, _vocab()) == []


def test_single_param_accepts_legacy_scalar() -> None:
    # colon-string / scalar single-param form is tolerated pre-A0.5.
    assert validate_conditions({"actor_has_flag": "vip"}, _vocab()) == []
    assert validate_effects([{"give_item": "brass_key"}], _vocab()) == []


def test_one_level_any_group_validates_members() -> None:
    v = _vocab()
    block: JsonValue = {
        "any": [
            {"actor_has_flag": "vip"},
            {"actor_reputation_at_least": {"faction": "city_watch", "value": 0}},
        ]
    }
    assert validate_conditions(block, v) == []


def test_any_group_flags_unknown_member() -> None:
    block: JsonValue = {"any": [{"actor_has_flag": "vip"}, {"bogus_condition": True}]}
    issues = validate_conditions(block, _vocab())
    assert len(issues) == 1
    assert "unknown condition 'bogus_condition'" in issues[0].message
    assert issues[0].location == "when.any[1]"


def test_nested_boolean_groups_beyond_one_level_flagged() -> None:
    block: JsonValue = {"all": [{"any": [{"actor_has_flag": "vip"}]}]}
    issues = validate_conditions(block, _vocab())
    assert any("nested boolean groups beyond one level" in i.message for i in issues)


def test_dict_and_list_shapes_both_accepted() -> None:
    v = _vocab()
    # effects as a map (dialogue style) and as a list (trigger style)
    assert validate_effects({"give_item": "brass_key"}, v) == []
    assert validate_effects([{"give_item": "brass_key"}], v) == []
