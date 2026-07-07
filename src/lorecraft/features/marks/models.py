"""Mark definitions: schema, loader, registry, content-lint (Sprint 53).

Marks are named passive badges earned by *discovering* things — a progression
track fed by exploration, not combat. Definitions are *content* (like
rooms/items/hunts), authored in `world_content/marks.yaml` and loaded into an
in-memory registry at startup — the hunts-def pattern. Earned state is a
player flag (`mark:<id>`, see `earned_flag`), following the `hunt:*` / `lore:*`
flag conventions; criteria read the journal state already on `Player`
(`visited_rooms`, `met_npcs`, `discovered_items`, `flags`).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from lorecraft.engine.game.modifiers import ModifierKind

MARKS_SCHEMA_VERSION = 1

EARNED_FLAG_PREFIX = "mark:"


def earned_flag(mark_id: str) -> str:
    """The player flag recording that a mark has been earned."""
    return f"{EARNED_FLAG_PREFIX}{mark_id}"


class MarkBoon(BaseModel):
    """One modifier a mark contributes once earned (engine_core.md §3.5).

    Keep boons modest and flat — the soft-cap principle. `mult` amounts are
    factors (1.1 = +10%), never fractions to add.
    """

    key: str
    kind: ModifierKind = "add"
    amount: float

    @field_validator("key")
    @classmethod
    def _key_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("boon.key must be non-empty")
        return value

    @field_validator("amount")
    @classmethod
    def _amount_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("boon.amount must be finite")
        return value

    @model_validator(mode="after")
    def _mult_positive(self) -> MarkBoon:
        if self.kind == "mult" and self.amount <= 0:
            raise ValueError("boon.amount must be > 0 for kind=mult")
        return self


class MarkCriteria(BaseModel):
    """What must be true of the player's journal state to earn the mark.

    Every populated criterion must hold (AND). At least one must be populated.
    """

    rooms_visited: list[str] = Field(default_factory=list)
    rooms_visited_count: int = 0
    npcs_met: list[str] = Field(default_factory=list)
    items_discovered: list[str] = Field(default_factory=list)
    flags_set: list[str] = Field(default_factory=list)

    @field_validator("rooms_visited_count")
    @classmethod
    def _count_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("criteria.rooms_visited_count must be >= 0")
        return value

    @model_validator(mode="after")
    def _at_least_one(self) -> MarkCriteria:
        if not (
            self.rooms_visited
            or self.rooms_visited_count
            or self.npcs_met
            or self.items_discovered
            or self.flags_set
        ):
            raise ValueError("mark criteria must set at least one condition")
        return self


class MarkDef(BaseModel):
    id: str
    name: str
    description: str = ""
    criteria: MarkCriteria
    boons: list[MarkBoon] = Field(default_factory=list)
    hidden: bool = False  # hidden marks are omitted from "???" teasers until earned


class MarksDocument(BaseModel):
    version: int = MARKS_SCHEMA_VERSION
    marks: list[MarkDef] = Field(default_factory=list)

    @field_validator("marks")
    @classmethod
    def _unique_ids(cls, marks: list[MarkDef]) -> list[MarkDef]:
        ids = [m.id for m in marks]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate mark ids: {sorted(dupes)}")
        return marks


def validate_marks_document(data: object) -> MarksDocument:
    return MarksDocument.model_validate(data)


def load_marks_yaml(path: str | Path) -> MarksDocument:
    text = Path(path).read_text()
    return validate_marks_document(yaml.safe_load(text) or {})


def lint_marks(
    document: MarksDocument,
    *,
    known_room_ids: Iterable[str],
    known_npc_ids: Iterable[str],
    known_item_ids: Iterable[str],
) -> list[str]:
    """Content-lint: return human-readable problems (empty = clean).

    Checks that every room/NPC/item a mark's criteria reference resolves to
    real world content — the same fail-fast contract as hunt/room/item linting.
    Flags are free-form by design (dialogue side effects mint them), so
    `flags_set` is not checked.
    """
    rooms = set(known_room_ids)
    npcs = set(known_npc_ids)
    items = set(known_item_ids)
    problems: list[str] = []
    for mark in document.marks:
        for room_id in mark.criteria.rooms_visited:
            if room_id not in rooms:
                problems.append(
                    f"mark {mark.id!r}: criteria room {room_id!r} is not a known room"
                )
        for npc_id in mark.criteria.npcs_met:
            if npc_id not in npcs:
                problems.append(
                    f"mark {mark.id!r}: criteria npc {npc_id!r} is not a known npc"
                )
        for item_id in mark.criteria.items_discovered:
            if item_id not in items:
                problems.append(
                    f"mark {mark.id!r}: criteria item {item_id!r} is not a known item"
                )
    return problems


class MarkRegistry:
    def __init__(self) -> None:
        self._marks: dict[str, MarkDef] = {}

    def register(self, mark: MarkDef) -> None:
        self._marks[mark.id] = mark

    def load_document(self, document: MarksDocument) -> None:
        for mark in document.marks:
            self.register(mark)

    def get(self, mark_id: str) -> MarkDef | None:
        return self._marks.get(mark_id)

    def all(self) -> list[MarkDef]:
        return list(self._marks.values())

    def clear(self) -> None:
        self._marks.clear()


_registry = MarkRegistry()


def get_registry() -> MarkRegistry:
    return _registry
