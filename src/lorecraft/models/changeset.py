"""World versioning table definitions."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class Changeset(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    status: str = "draft"
    created_by: str
    created_at: float
    promoted_at: float | None = None
    world_version: str | None = None


class ChangesetItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    changeset_id: str = Field(index=True)
    entity_type: str
    entity_id: str
    operation: str
    before_state: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    after_state: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))


class WorldMigration(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    from_version: int
    to_version: int
    migration_type: str
    payload: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    applied_at: float


class ConflictScanResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    changeset_id: str = Field(index=True)
    entity_type: str
    entity_id: str
    severity: str
    auto_resolvable: bool
    acknowledged: bool = False
    description: str
