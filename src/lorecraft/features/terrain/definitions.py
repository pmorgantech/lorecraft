"""Terrain types on rooms (Sprint 25.2).

Data-driven, like equipment slots — a world can extend this set without
engine edits. Terrain can require a minimum skill level to enter (gated at
the command layer in services/movement.py) and layers an extra description
line onto `look`/`examine`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TerrainDef:
    name: str
    description_suffix: str
    # The discipline whose rank gates safe entry (Sprint 78; renamed from the
    # pre-78 `required_skill`). Its id doubles as the `skill.<name>` resolver key
    # for the gated check (survival). None = ungated terrain.
    required_discipline: str | None = None
    required_discipline_min: int = 0


class TerrainRegistry:
    def __init__(self) -> None:
        self._defs: dict[str, TerrainDef] = {}

    def register(self, terrain_def: TerrainDef) -> None:
        self._defs[terrain_def.name] = terrain_def

    def get(self, name: str) -> TerrainDef | None:
        return self._defs.get(name)


_registry = TerrainRegistry()


def get_registry() -> TerrainRegistry:
    return _registry


STANDARD_TERRAIN = [
    TerrainDef("normal", ""),
    TerrainDef("road", "The road is well-traveled and easy going."),
    TerrainDef("forest", "Dense undergrowth slows your steps."),
    TerrainDef(
        "mountain",
        "The mountain path is steep and treacherous.",
        required_discipline="survival",
        required_discipline_min=20,
    ),
    TerrainDef(
        "swamp",
        "The ground squelches underfoot, thick with mud.",
        required_discipline="survival",
        required_discipline_min=10,
    ),
    TerrainDef(
        "water",
        "The water is cold and deep.",
        required_discipline="survival",
        required_discipline_min=30,
    ),
]

for _terrain_def in STANDARD_TERRAIN:
    _registry.register(_terrain_def)
