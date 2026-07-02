"""Repo-tracked issue tracking: bugs, todos, and feature requests."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class Issue(SQLModel, table=True):
    id: str = Field(primary_key=True)
    type: str = "bug"  # bug | todo | feature
    title: str
    description: str = ""
    status: str = "open"  # open | in-progress | resolved | deferred | duplicate
    priority: str = "normal"  # low | normal | high | critical
    component: str = ""
    created_by: str = ""
    assigned_to: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    links: list[JsonObject] = Field(default_factory=list, sa_column=Column(JSON))
