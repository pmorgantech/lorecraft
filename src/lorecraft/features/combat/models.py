"""Scheduled Intent combat table definitions."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class CombatEncounter(SQLModel, table=True):
    id: str = Field(primary_key=True)
    location_id: str = Field(index=True)
    state: str = Field(default="active", index=True)
    started_at_game_time: float
    started_at_real_time: float
    version: int = 1
    ruleset_id: str = "default"
    combat_mode: str = "scheduled_intent"
    last_hostile_action_at: float
    ended_at_game_time: float | None = None


class CombatParticipant(SQLModel, table=True):
    id: str = Field(primary_key=True)
    encounter_id: str = Field(foreign_key="combatencounter.id", index=True)
    actor_type: str = Field(index=True)
    actor_id: str = Field(index=True)
    side_id: str = Field(index=True)
    joined_at: float
    status: str = Field(default="active", index=True)
    primary_ready_at: float = 0.0
    reaction_ready_at: float = 0.0
    queued_action_id: str | None = None
    position: str = "engaged"
    stance: str = "balanced"
    threat: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    contribution: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))


class CombatRelationship(SQLModel, table=True):
    id: str = Field(primary_key=True)
    encounter_id: str = Field(foreign_key="combatencounter.id", index=True)
    source_participant_id: str = Field(foreign_key="combatparticipant.id", index=True)
    target_participant_id: str = Field(foreign_key="combatparticipant.id", index=True)
    hostility: str = "hostile"
    engagement: str = "engaged"
    visibility: str = "visible"


class CombatAction(SQLModel, table=True):
    id: str = Field(primary_key=True)
    encounter_id: str = Field(foreign_key="combatencounter.id", index=True)
    actor_participant_id: str = Field(foreign_key="combatparticipant.id", index=True)
    actor_type: str
    actor_id: str = Field(index=True)
    target_participant_id: str | None = Field(
        default=None, foreign_key="combatparticipant.id", index=True
    )
    target_type: str | None = None
    target_id: str | None = Field(default=None, index=True)
    action_key: str
    channel: str = "primary"
    state: str = Field(default="pending", index=True)
    submitted_at: float
    resolve_at: float
    recovery_until: float
    replaced_by_action_id: str | None = None
    outcome: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    random_trace: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))


class CombatResolutionRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    encounter_id: str = Field(foreign_key="combatencounter.id", index=True)
    action_id: str = Field(foreign_key="combataction.id", index=True)
    actor_type: str
    actor_id: str = Field(index=True)
    target_type: str | None = None
    target_id: str | None = Field(default=None, index=True)
    action_key: str
    outcome: str
    damage: float = 0.0
    resolved_at_game_time: float
    ruleset_id: str = "default"
    resolver_version: str = "opposed-v1"
    random_trace: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    damage_trace: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    payload: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
