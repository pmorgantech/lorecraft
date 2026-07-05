"""Repo-tracked help topics: YAML schema, DB import, and DB->YAML export.

Mirrors `lorecraft.content.news`: `docs/help_topics.yaml` is the git-tracked
source of truth, imported into the DB on startup when the DB has no topics yet,
and re-exported to YAML whenever the admin UI mutates a topic.

Each topic carries a stable numeric ``id`` and a unique ``name`` so it can be
referenced either way (`help 3` or `help combat`).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import Session, col, select
import yaml

from lorecraft.content.paths import resolve_repo_path
from lorecraft.models.help import HelpTopic

log = logging.getLogger(__name__)

FORMAT_VERSION = "1.0"

_SLUG_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789-_")


class HelpValidationError(ValueError):
    """Raised when authored help YAML is structurally invalid."""


class HelpTopicData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    title: str
    body: str = ""
    category: str = ""
    keywords: list[str] = Field(default_factory=list)


class HelpDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: str = FORMAT_VERSION
    topics: list[HelpTopicData] = Field(default_factory=list)


def validate_help_document(data: object) -> HelpDocument:
    try:
        document = HelpDocument.model_validate(data)
    except ValidationError as exc:
        raise HelpValidationError(str(exc)) from exc

    ids = [t.id for t in document.topics]
    dup_ids = {i for i in ids if ids.count(i) > 1}
    if dup_ids:
        raise HelpValidationError(f"duplicate help topic ids: {sorted(dup_ids)}")

    names = [t.name.lower() for t in document.topics]
    dup_names = {n for n in names if names.count(n) > 1}
    if dup_names:
        raise HelpValidationError(f"duplicate help topic names: {sorted(dup_names)}")

    for topic in document.topics:
        if topic.id < 1:
            raise HelpValidationError(f"help topic id must be >= 1 (got {topic.id})")
        if not topic.name or any(c not in _SLUG_ALLOWED for c in topic.name.lower()):
            raise HelpValidationError(
                f"help topic name {topic.name!r} must be a slug "
                "(letters, digits, '-' or '_')"
            )

    return document


def load_help_yaml(path: str | Path, session: Session) -> HelpDocument:
    source_path = Path(path)
    data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    document = validate_help_document(cast(object, data))
    import_help(document, session)
    return document


def import_help(document: HelpDocument, session: Session) -> None:
    for topic in document.topics:
        session.merge(
            HelpTopic(
                id=topic.id,
                name=topic.name.lower(),
                title=topic.title,
                body=topic.body,
                category=topic.category,
                keywords=[k.lower() for k in topic.keywords],
            )
        )


def export_help_yaml(session: Session, path: str | Path) -> None:
    """Write all help topics currently in the DB back to the YAML file."""
    topics = session.exec(select(HelpTopic).order_by(col(HelpTopic.id))).all()
    document: dict[str, object] = {
        "format_version": FORMAT_VERSION,
        "topics": [
            {
                "id": t.id,
                "name": t.name,
                "title": t.title,
                "body": t.body,
                "category": t.category,
                "keywords": list(t.keywords),
            }
            for t in topics
        ],
    }
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def ensure_help_bootstrapped(session: Session, help_yaml_path: str) -> None:
    """Import `docs/help_topics.yaml` into the DB the first time it has no topics.

    Once topics exist in the DB, the YAML is a mirror kept in sync by
    `export_help_yaml` on admin mutation, not re-imported on startup.
    """
    has_topics = session.exec(select(HelpTopic)).first() is not None
    if has_topics:
        return
    resolved_path = resolve_repo_path(help_yaml_path)
    if not resolved_path.is_file():
        log.warning("Help topics YAML not found: %s", resolved_path)
        return
    log.info("Importing help topics from %s", resolved_path)
    load_help_yaml(resolved_path, session)
