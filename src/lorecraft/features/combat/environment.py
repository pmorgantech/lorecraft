"""Room environment modifiers for combat resolution.

Sprint 88.2 keeps terrain/cover deliberately narrow: room environment only
adjusts the target's opposed defense score and records the applied pieces in
the resolution trace. It does not add positions, formations, or cover actions.
"""

from __future__ import annotations

from dataclasses import dataclass

from lorecraft.engine.models.world import Room
from lorecraft.types import JsonObject

TERRAIN_DEFENSE_BONUSES: dict[str, int] = {
    "forest": 2,
    "mountain": 2,
    "swamp": 1,
}

COVER_DEFENSE_BONUSES: dict[str, int] = {
    "light": 1,
    "partial": 2,
    "heavy": 4,
}


@dataclass(frozen=True)
class EnvironmentalDefense:
    bonus: int
    trace: JsonObject


def environmental_defense_for(room: Room | None) -> EnvironmentalDefense:
    if room is None:
        return EnvironmentalDefense(
            bonus=0,
            trace={
                "terrain": None,
                "terrain_defense_bonus": 0,
                "cover": None,
                "cover_defense_bonus": 0,
                "environment_defense_bonus": 0,
            },
        )
    terrain_bonus = _numeric_flag(
        room.flags, "combat_terrain_defense_bonus", default=None
    )
    if terrain_bonus is None:
        terrain_bonus = TERRAIN_DEFENSE_BONUSES.get(room.terrain, 0)
    cover, cover_bonus = _cover_bonus(room.flags)
    total = int(terrain_bonus) + cover_bonus
    return EnvironmentalDefense(
        bonus=total,
        trace={
            "terrain": room.terrain,
            "terrain_defense_bonus": int(terrain_bonus),
            "cover": cover,
            "cover_defense_bonus": cover_bonus,
            "environment_defense_bonus": total,
        },
    )


def _cover_bonus(flags: JsonObject) -> tuple[str | None, int]:
    direct = _numeric_flag(flags, "combat_cover_defense_bonus", default=None)
    if direct is not None:
        return "custom", int(direct)

    cover = flags.get("combat_cover")
    if isinstance(cover, dict):
        label = cover.get("label")
        bonus = _numeric_flag(cover, "defense_bonus", default=0)
        return str(label) if label is not None else "custom", int(bonus or 0)
    if isinstance(cover, str):
        key = cover.strip().casefold()
        return key or None, COVER_DEFENSE_BONUSES.get(key, 0)
    return None, 0


def _numeric_flag(flags: JsonObject, key: str, *, default: int | None) -> int | None:
    value = flags.get(key, default)
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default
