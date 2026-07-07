"""Sprint 53.1: mark definitions — schema, loader, registry, content-lint."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lorecraft.features.marks.models import (
    MarkDef,
    MarkRegistry,
    earned_flag,
    lint_marks,
    load_marks_yaml,
    validate_marks_document,
)


def _mark(mark_id: str = "wanderer", **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": mark_id,
        "name": "Mark of the Wanderer",
        "description": "Walked the breadth of Ashmoore.",
        "criteria": {"rooms_visited": ["village_square"]},
    }
    base.update(overrides)
    return base


class TestSchema:
    def test_minimal_mark_validates(self) -> None:
        doc = validate_marks_document({"marks": [_mark()]})
        assert doc.marks[0].id == "wanderer"
        assert doc.marks[0].hidden is False
        assert doc.marks[0].boons == []

    def test_empty_criteria_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at least one condition"):
            validate_marks_document({"marks": [_mark(criteria={})]})

    def test_duplicate_ids_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate mark ids"):
            validate_marks_document({"marks": [_mark(), _mark()]})

    def test_negative_rooms_visited_count_rejected(self) -> None:
        with pytest.raises(ValidationError, match="rooms_visited_count"):
            validate_marks_document(
                {"marks": [_mark(criteria={"rooms_visited_count": -1})]}
            )

    def test_count_only_criteria_validates(self) -> None:
        doc = validate_marks_document(
            {"marks": [_mark(criteria={"rooms_visited_count": 5})]}
        )
        assert doc.marks[0].criteria.rooms_visited_count == 5

    def test_bad_boon_kind_rejected(self) -> None:
        with pytest.raises(ValidationError, match="boon.kind"):
            validate_marks_document(
                {
                    "marks": [
                        _mark(
                            boons=[
                                {"key": "skill.perception", "kind": "pow", "amount": 1}
                            ]
                        )
                    ]
                }
            )

    def test_non_positive_mult_boon_rejected(self) -> None:
        with pytest.raises(ValidationError, match="mult"):
            validate_marks_document(
                {
                    "marks": [
                        _mark(boons=[{"key": "price.buy", "kind": "mult", "amount": 0}])
                    ]
                }
            )

    def test_boon_defaults_to_add(self) -> None:
        doc = validate_marks_document(
            {"marks": [_mark(boons=[{"key": "skill.perception", "amount": 1}])]}
        )
        assert doc.marks[0].boons[0].kind == "add"


class TestLoader:
    def test_load_yaml_file(self, tmp_path: object) -> None:
        path = tmp_path / "marks.yaml"  # type: ignore[operator]
        path.write_text(
            """
version: 1
marks:
  - id: wanderer
    name: Mark of the Wanderer
    criteria:
      rooms_visited_count: 3
"""
        )
        doc = load_marks_yaml(path)
        assert [m.id for m in doc.marks] == ["wanderer"]

    def test_empty_file_loads_no_marks(self, tmp_path: object) -> None:
        path = tmp_path / "marks.yaml"  # type: ignore[operator]
        path.write_text("")
        assert load_marks_yaml(path).marks == []


class TestLint:
    def test_unknown_references_reported(self) -> None:
        doc = validate_marks_document(
            {
                "marks": [
                    _mark(
                        criteria={
                            "rooms_visited": ["nowhere"],
                            "npcs_met": ["nobody"],
                            "items_discovered": ["nothing"],
                        }
                    )
                ]
            }
        )
        problems = lint_marks(
            doc,
            known_room_ids=["here"],
            known_npc_ids=["mira"],
            known_item_ids=["coin"],
        )
        assert len(problems) == 3
        assert any("'nowhere'" in p for p in problems)
        assert any("'nobody'" in p for p in problems)
        assert any("'nothing'" in p for p in problems)

    def test_clean_document_lints_clean(self) -> None:
        doc = validate_marks_document(
            {
                "marks": [
                    _mark(
                        criteria={
                            "rooms_visited": ["here"],
                            "npcs_met": ["mira"],
                            "items_discovered": ["coin"],
                            "flags_set": ["lore:anything"],  # flags are free-form
                        }
                    )
                ]
            }
        )
        assert (
            lint_marks(
                doc,
                known_room_ids=["here"],
                known_npc_ids=["mira"],
                known_item_ids=["coin"],
            )
            == []
        )


class TestRegistry:
    def test_load_get_all_clear(self) -> None:
        registry = MarkRegistry()
        doc = validate_marks_document({"marks": [_mark(), _mark("seeker")]})
        registry.load_document(doc)
        assert registry.get("wanderer") is not None
        assert registry.get("missing") is None
        assert {m.id for m in registry.all()} == {"wanderer", "seeker"}
        registry.clear()
        assert registry.all() == []

    def test_reregister_replaces(self) -> None:
        registry = MarkRegistry()
        registry.register(MarkDef.model_validate(_mark()))
        renamed = MarkDef.model_validate(_mark(name="Renamed"))
        registry.register(renamed)
        got = registry.get("wanderer")
        assert got is not None and got.name == "Renamed"


def test_earned_flag_convention() -> None:
    assert earned_flag("wanderer") == "mark:wanderer"
