"""Scavenger-hunt definitions: schema, loader, registry, content-lint.

Hunt definitions are *content* (like rooms/items), authored in
`world_content/hunts.yaml` and loaded into an in-memory registry at startup —
the terrain/weather-def pattern. See `docs/scavenger_hunt.md`.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

HUNTS_SCHEMA_VERSION = 1


class HuntReward(BaseModel):
    coins: int = 0
    lore: str | None = None  # sets flag lore:<lore>, journal-visible

    @field_validator("coins")
    @classmethod
    def _coins_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("reward.coins must be >= 0")
        return value


class HuntDef(BaseModel):
    id: str
    name: str
    description: str = ""
    clue_items: list[str] = Field(min_length=1)
    spawn_rooms: list[str] = Field(min_length=1)
    reward: HuntReward = Field(default_factory=HuntReward)
    duration_ticks: int = 240

    @field_validator("duration_ticks")
    @classmethod
    def _duration_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("duration_ticks must be > 0")
        return value


class HuntsDocument(BaseModel):
    version: int = HUNTS_SCHEMA_VERSION
    hunts: list[HuntDef] = Field(default_factory=list)

    @field_validator("hunts")
    @classmethod
    def _unique_ids(cls, hunts: list[HuntDef]) -> list[HuntDef]:
        ids = [h.id for h in hunts]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate hunt ids: {sorted(dupes)}")
        return hunts


def validate_hunts_document(data: object) -> HuntsDocument:
    return HuntsDocument.model_validate(data)


def load_hunts_yaml(path: str | Path) -> HuntsDocument:
    text = Path(path).read_text()
    return validate_hunts_document(yaml.safe_load(text) or {})


def lint_hunts(
    document: HuntsDocument,
    *,
    known_item_ids: Iterable[str],
    known_room_ids: Iterable[str],
) -> list[str]:
    """Content-lint: return human-readable problems (empty = clean).

    Checks that every clue item and spawn room a hunt references resolves to
    real world content — the same fail-fast contract as room/item linting.
    """
    items = set(known_item_ids)
    rooms = set(known_room_ids)
    problems: list[str] = []
    for hunt in document.hunts:
        for item_id in hunt.clue_items:
            if item_id not in items:
                problems.append(
                    f"hunt {hunt.id!r}: clue item {item_id!r} is not a known item"
                )
        for room_id in hunt.spawn_rooms:
            if room_id not in rooms:
                problems.append(
                    f"hunt {hunt.id!r}: spawn room {room_id!r} is not a known room"
                )
    return problems


class HuntRegistry:
    def __init__(self) -> None:
        self._hunts: dict[str, HuntDef] = {}

    def register(self, hunt: HuntDef) -> None:
        self._hunts[hunt.id] = hunt

    def load_document(self, document: HuntsDocument) -> None:
        for hunt in document.hunts:
            self.register(hunt)

    def get(self, hunt_id: str) -> HuntDef | None:
        return self._hunts.get(hunt_id)

    def all(self) -> list[HuntDef]:
        return list(self._hunts.values())

    def clear(self) -> None:
        self._hunts.clear()


_registry = HuntRegistry()


def get_registry() -> HuntRegistry:
    return _registry
