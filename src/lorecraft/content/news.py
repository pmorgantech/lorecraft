"""Repo-tracked news/announcements: YAML schema, DB import, and DB->YAML export.

Mirrors `lorecraft.content.issues`: `docs/news.yaml` is the git-tracked source
of truth, imported into the DB on startup when the DB has no news yet, and
re-exported to YAML whenever the admin UI mutates an announcement.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import Session, select
import yaml

from lorecraft.content.paths import resolve_repo_path
from lorecraft.models.news import NewsItem

log = logging.getLogger(__name__)

FORMAT_VERSION = "1.0"


class NewsValidationError(ValueError):
    """Raised when authored news YAML is structurally invalid."""


class NewsItemData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str = "bulletin"  # server | event | bulletin | maintenance | patch
    title: str
    body: str = ""
    author: str = ""
    published_at: datetime | None = None
    expires_at: datetime | None = None
    priority: str = "normal"  # low | normal | high
    icon: str = ""
    tags: list[str] = Field(default_factory=list)


class NewsDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: str = FORMAT_VERSION
    announcements: list[NewsItemData] = Field(default_factory=list)


def validate_news_document(data: object) -> NewsDocument:
    try:
        document = NewsDocument.model_validate(data)
    except ValidationError as exc:
        raise NewsValidationError(str(exc)) from exc

    ids = [item.id for item in document.announcements]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise NewsValidationError(f"duplicate news ids: {sorted(duplicates)}")

    for item in document.announcements:
        if (
            item.expires_at is not None
            and item.published_at is not None
            and item.expires_at <= item.published_at
        ):
            raise NewsValidationError(
                f"news {item.id} expires_at must be after published_at"
            )

    return document


def _to_epoch(value: datetime | None, *, default_now: bool) -> float | None:
    if value is None:
        return datetime.now(timezone.utc).timestamp() if default_now else None
    return value.timestamp()


def to_iso(value: float) -> str:
    return (
        datetime.fromtimestamp(value, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_news_yaml(path: str | Path, session: Session) -> NewsDocument:
    source_path = Path(path)
    data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    document = validate_news_document(cast(object, data))
    import_news(document, session)
    return document


def import_news(document: NewsDocument, session: Session) -> None:
    for item in document.announcements:
        published_at = _to_epoch(item.published_at, default_now=True)
        assert published_at is not None
        session.merge(
            NewsItem(
                id=item.id,
                type=item.type,
                title=item.title,
                body=item.body,
                author=item.author,
                published_at=published_at,
                expires_at=_to_epoch(item.expires_at, default_now=False),
                priority=item.priority,
                icon=item.icon,
                tags=list(item.tags),
            )
        )


def export_news_yaml(session: Session, path: str | Path) -> None:
    """Write all news currently in the DB back to the repo-tracked YAML file."""
    items = session.exec(select(NewsItem).order_by(NewsItem.id)).all()
    document: dict[str, object] = {
        "format_version": FORMAT_VERSION,
        "announcements": [
            {
                "id": item.id,
                "type": item.type,
                "title": item.title,
                "body": item.body,
                "author": item.author,
                "published_at": to_iso(item.published_at),
                "expires_at": to_iso(item.expires_at)
                if item.expires_at is not None
                else None,
                "priority": item.priority,
                "icon": item.icon,
                "tags": list(item.tags),
            }
            for item in items
        ],
    }
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def ensure_news_bootstrapped(session: Session, news_yaml_path: str) -> None:
    """Import `docs/news.yaml` into the DB the first time it has no news.

    Once news exist in the DB, the YAML file is a mirror kept in sync by
    `export_news_yaml` on every admin mutation, not re-imported on startup.
    """
    has_news = session.exec(select(NewsItem)).first() is not None
    if has_news:
        return
    resolved_path = resolve_repo_path(news_yaml_path)
    if not resolved_path.is_file():
        log.warning("News YAML not found: %s", resolved_path)
        return
    log.info("Importing news from %s", resolved_path)
    load_news_yaml(resolved_path, session)
