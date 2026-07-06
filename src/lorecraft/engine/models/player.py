"""Player and save slot table definitions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class Player(SQLModel, table=True):
    id: str = Field(primary_key=True)
    username: str = Field(index=True, unique=True)
    current_room_id: str
    visited_rooms: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    met_npcs: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # First-discovered item *definitions* (Sprint 46): set on first take/examine,
    # same pattern as met_npcs. Per-definition, not per-instance — finding a
    # second copper coin doesn't re-record. Surfaced by the journal.
    discovered_items: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    flags: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    respawn_room_id: str
    pvp_consent: bool = False
    world_schema_version: int = 1
    active_combat_session_id: str | None = None
    ghost_state: bool = False
    # Opaque per-account presentation preferences blob. The engine stores it
    # without interpreting it; the web host (webui/player/preferences.py) owns
    # the schema, defaults, and validation, keeping display concerns out of
    # Tier 1. Empty {} means "all defaults".
    preferences: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))


class PlayerStats(SQLModel, table=True):
    player_id: str = Field(primary_key=True, foreign_key="player.id")
    strength: int = 10
    agility: int = 10
    vitality: int = 10
    intellect: int = 10
    presence: int = 10
    fortitude: int = 10
    # Definitional base (Sprint 19, engine_core.md §3.3): fed to the "hp" MeterDef's
    # base_maximum. Runtime hp is Meter(entity, "hp") — current_hp is deleted, not
    # deprecated (PlayerStats.current_hp used to hold it).
    max_hp: int = 100
    level: int = 1
    xp: int = 0
    xp_to_next: int = 100
    skills: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    # Innate traits (Sprint 19 adds the column; Tier 2 populates it — empty by default).
    traits: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class SaveSlot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    player_id: str = Field(index=True)
    slot_name: str
    saved_at: float
    room_id: str
    # v2 (Sprint 16): list of {item_id, quantity, instance_id} dicts, one per carried
    # stack. v1 saves store a flat list[str] of item ids (one entry per unit) —
    # SaveSlotService.load() converts on read; old saves must not break. Typed as
    # list[Any] (not list[JsonValue]) — pydantic's forward-ref resolution recurses
    # infinitely on a bare list[JsonValue] field (JsonValue is self-referential);
    # dict[str, JsonValue] (JsonObject) is fine, only the direct list form isn't.
    inventory: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    visited_rooms: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    met_npcs: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    discovered_items: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    flags: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    stats_snapshot: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    quest_progress: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    timeline_branch_id: str | None = None
