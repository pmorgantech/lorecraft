"""Repo-tracked in-game help topics (articles).

Topics are authored reference content (like news/issues): the git-tracked
`docs/help_topics.yaml` is the source of truth, imported into the DB on first
startup and re-exported when the admin UI mutates one. Each topic has both a
stable numeric ``id`` and a unique short ``name`` so players can pull it up by
either (`help 3` or `help combat`).
"""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class HelpTopic(SQLModel, table=True):
    # Numeric id: shown in listings as "[id] name" and usable as `help <id>`.
    id: int = Field(primary_key=True)
    # Short unique slug, e.g. "combat" — usable as `help <name>`.
    name: str = Field(index=True, unique=True)
    title: str
    body: str = ""
    # Grouping label for organizing the topic list (e.g. "Basics", "Combat").
    category: str = ""
    # Extra search terms so a topic is findable by words other than its name.
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
