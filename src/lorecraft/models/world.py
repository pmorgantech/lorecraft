"""World state table definitions."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class Room(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    map_x: int
    map_y: int
    area_id: str | None = None
    is_active: bool = True
    fallback_room_id: str | None = None
    flags: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    disabled_commands: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    light_level: int = 1
    version: int = 1
    terrain: str = (
        "normal"  # affects travel gating; see game/terrain.py's TerrainRegistry
    )


class Exit(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    room_id: str = Field(foreign_key="room.id", index=True)
    direction: str
    target_room_id: str
    locked: bool = False
    key_item_id: str | None = None
    hidden: bool = False
    condition_flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class Item(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    takeable: bool = True
    tradeable: bool = True
    bound: bool = False  # Sprint 16: soulbound items can't be dropped/sold/traded (enforced by Tier 2 rules)
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    usable_with: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    loot_table: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    slot: str | None = (
        None  # equipment slot key (head, hands, main_hand, etc.); None = not equippable
    )
    wearable: bool = False  # worn (armor/clothing) vs. wielded (weapon/tool/light)
    weight: float = 0.0  # item weight; drives encumbrance
    quality: str = (
        "common"  # common|fine|superior|rare|legendary — affects value & trade
    )
    max_durability: int | None = (
        None  # None = indestructible; else tracked per-instance via component
    )
    light: int = 0  # light radius/level this item emits when equipped & lit
    capacity: float | None = (
        None  # if set, item is a container holding up to capacity weight
    )
    effects: list[JsonObject] = Field(
        default_factory=list, sa_column=Column(JSON)
    )  # effect descriptors (registry-driven)


class WorldMeta(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    schema_version: int = 1
    engine_version: str = "0.1.0"


class WorldClock(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_epoch: float
    real_epoch: float
    time_ratio: float = 60.0
    paused: bool = False
    current_hour: int = 8
    current_minute: int = 0
    current_day: int = 1
    current_season: str = "spring"
    weather: str = "clear"


class NPC(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    current_room_id: str
    home_room_id: str
    dialogue_tree_id: str
    behavior: str = "defensive"
    # Definitional base (Sprint 19); runtime hp is Meter("npc", id, "hp") — current_hp
    # is deleted, not deprecated.
    max_hp: int = 50
    loot_table: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    respawn_seconds: int | None = 300
    schedule: list[JsonObject] = Field(default_factory=list, sa_column=Column(JSON))
