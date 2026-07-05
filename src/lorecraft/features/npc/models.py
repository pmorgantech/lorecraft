"""Dialogue tree table definition."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class DialogueTree(SQLModel, table=True):
    id: str = Field(primary_key=True)
    tree_data: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
