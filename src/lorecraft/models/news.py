"""Repo-tracked in-game news and announcements."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class NewsItem(SQLModel, table=True):
    id: str = Field(primary_key=True)
    type: str = "bulletin"  # server | event | bulletin | maintenance | patch
    title: str
    body: str = ""
    author: str = ""
    published_at: float = 0.0
    expires_at: float | None = None
    priority: str = "normal"  # low | normal | high
    icon: str = ""
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
