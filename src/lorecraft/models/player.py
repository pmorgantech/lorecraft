"""Player and save slot table definitions."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class Player(SQLModel, table=True):
    id: str = Field(primary_key=True)
    username: str = Field(index=True, unique=True)
    current_room_id: str
    inventory: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    visited_rooms: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    flags: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    respawn_room_id: str
    pvp_consent: bool = False
    world_schema_version: int = 1
    active_combat_session_id: str | None = None
    ghost_state: bool = False


class PlayerStats(SQLModel, table=True):
    player_id: str = Field(primary_key=True, foreign_key="player.id")
    strength: int = 10
    agility: int = 10
    vitality: int = 10
    intellect: int = 10
    presence: int = 10
    fortitude: int = 10
    max_hp: int = 100
    current_hp: int = 100
    level: int = 1
    xp: int = 0
    xp_to_next: int = 100
    skills: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))


class SaveSlot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    player_id: str = Field(index=True)
    slot_name: str
    saved_at: float
    room_id: str
    inventory: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    flags: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    stats_snapshot: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    quest_progress: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    timeline_branch_id: str | None = None
