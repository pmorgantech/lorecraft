"""Discipline definition loading + validation (Sprint 78.1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lorecraft.features.disciplines.abilities import (
    DEFAULT_IMPROVE_CHANCE,
    DEFAULT_MAX_RANK,
    DisciplineRegistry,
    validate_discipline_document,
)


def _discipline(discipline_id: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": discipline_id,
        "name": discipline_id.title(),
        "governing_stat": "fortitude",
    }
    base.update(overrides)
    return base


def test_loads_valid_document_with_defaulted_dials() -> None:
    doc = validate_discipline_document(
        {"version": 1, "disciplines": [_discipline("survival")]}
    )
    assert [d.id for d in doc.disciplines] == ["survival"]
    survival = doc.disciplines[0]
    assert survival.improve_chance == DEFAULT_IMPROVE_CHANCE
    assert survival.max_rank == DEFAULT_MAX_RANK


def test_per_discipline_dial_overrides_are_honoured() -> None:
    doc = validate_discipline_document(
        {"disciplines": [_discipline("subterfuge", improve_chance=0.25, max_rank=50)]}
    )
    assert doc.disciplines[0].improve_chance == 0.25
    assert doc.disciplines[0].max_rank == 50


def test_registry_round_trip() -> None:
    doc = validate_discipline_document(
        {"disciplines": [_discipline("commerce"), _discipline("rhetoric")]}
    )
    registry = DisciplineRegistry()
    registry.load_document(doc)
    assert "commerce" in registry
    assert registry.get("rhetoric") is not None
    assert {d.id for d in registry.all()} == {"commerce", "rhetoric"}
    registry.clear()
    assert registry.get("commerce") is None


def test_duplicate_ids_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_discipline_document(
            {"disciplines": [_discipline("survival"), _discipline("survival")]}
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"improve_chance": 1.5},
        {"improve_chance": -0.1},
        {"max_rank": 0},
        {"id": ""},
        {"governing_stat": "  "},
    ],
)
def test_invalid_discipline_fields_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validate_discipline_document({"disciplines": [_discipline("bad", **overrides)]})
