"""Repo-tracked issue tracking: YAML schema, DB import, and DB->YAML export.

Mirrors the world YAML pattern (`lorecraft.world.loader`): `docs/issues.yaml` is
the git-tracked source of truth, imported into the DB on startup when the DB has
no issues yet, and re-exported to YAML whenever the admin UI mutates an issue.
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
from lorecraft.models.issue import Issue

log = logging.getLogger(__name__)

FORMAT_VERSION = "1.0"


class IssuesValidationError(ValueError):
    """Raised when authored issues YAML is structurally invalid."""


class IssueLinkData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    id: str


class IssueData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str = "bug"  # bug | todo | feature
    title: str
    description: str = ""
    created_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    status: str = "open"  # open | in-progress | resolved | deferred | duplicate
    priority: str = "normal"  # low | normal | high | critical
    component: str = ""
    tags: list[str] = Field(default_factory=list)
    assigned_to: str = ""
    links: list[IssueLinkData] = Field(default_factory=list)


class IssuesDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: str = FORMAT_VERSION
    issues: list[IssueData] = Field(default_factory=list)


def validate_issues_document(data: object) -> IssuesDocument:
    try:
        document = IssuesDocument.model_validate(data)
    except ValidationError as exc:
        raise IssuesValidationError(str(exc)) from exc

    ids = [issue.id for issue in document.issues]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise IssuesValidationError(f"duplicate issue ids: {sorted(duplicates)}")

    known_ids = set(ids)
    errors: list[str] = []
    for issue in document.issues:
        for link in issue.links:
            if link.id not in known_ids:
                errors.append(
                    f"issue {issue.id} link references missing issue {link.id}"
                )
    if errors:
        raise IssuesValidationError("; ".join(errors))

    return document


def _to_epoch(value: datetime | None) -> float:
    if value is None:
        return datetime.now(timezone.utc).timestamp()
    return value.timestamp()


def _to_iso(value: float) -> str:
    return (
        datetime.fromtimestamp(value, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_issues_yaml(path: str | Path, session: Session) -> IssuesDocument:
    source_path = Path(path)
    data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    document = validate_issues_document(cast(object, data))
    import_issues(document, session)
    return document


def import_issues(document: IssuesDocument, session: Session) -> None:
    for issue in document.issues:
        session.merge(
            Issue(
                id=issue.id,
                type=issue.type,
                title=issue.title,
                description=issue.description,
                status=issue.status,
                priority=issue.priority,
                component=issue.component,
                created_by=issue.created_by,
                assigned_to=issue.assigned_to,
                created_at=_to_epoch(issue.created_at),
                updated_at=_to_epoch(issue.updated_at or issue.created_at),
                tags=list(issue.tags),
                links=[link.model_dump() for link in issue.links],
            )
        )


def export_issues_yaml(session: Session, path: str | Path) -> None:
    """Write all issues currently in the DB back to the repo-tracked YAML file."""
    issues = session.exec(select(Issue).order_by(Issue.id)).all()
    document: dict[str, object] = {
        "format_version": FORMAT_VERSION,
        "issues": [
            {
                "id": issue.id,
                "type": issue.type,
                "title": issue.title,
                "description": issue.description,
                "created_by": issue.created_by,
                "created_at": _to_iso(issue.created_at),
                "updated_at": _to_iso(issue.updated_at),
                "status": issue.status,
                "priority": issue.priority,
                "component": issue.component,
                "tags": list(issue.tags),
                "assigned_to": issue.assigned_to,
                "links": list(issue.links),
            }
            for issue in issues
        ],
    }
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def ensure_issues_bootstrapped(session: Session, issues_yaml_path: str) -> None:
    """Import `docs/issues.yaml` into the DB the first time it has no issues.

    Once issues exist in the DB, the YAML file is a mirror kept in sync by
    `export_issues_yaml` on every admin mutation, not re-imported on startup.
    """
    has_issues = session.exec(select(Issue)).first() is not None
    if has_issues:
        return
    resolved_path = resolve_repo_path(issues_yaml_path)
    if not resolved_path.is_file():
        log.warning("Issues YAML not found: %s", resolved_path)
        return
    log.info("Importing issues from %s", resolved_path)
    load_issues_yaml(resolved_path, session)
