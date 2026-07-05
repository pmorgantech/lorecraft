"""Data access for repo-tracked issues."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, col, select

from lorecraft.models.issue import Issue
from lorecraft.engine.repos.base import Repository


class IssueRepo(Repository[Issue, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Issue)

    def list_filtered(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        component: str | None = None,
        type_: str | None = None,
        assigned_to: str | None = None,
    ) -> Sequence[Issue]:
        stmt = select(Issue).order_by(col(Issue.created_at).desc())
        if status:
            stmt = stmt.where(Issue.status == status)
        if priority:
            stmt = stmt.where(Issue.priority == priority)
        if component:
            stmt = stmt.where(Issue.component == component)
        if type_:
            stmt = stmt.where(Issue.type == type_)
        if assigned_to:
            stmt = stmt.where(Issue.assigned_to == assigned_to)
        return self.session.exec(stmt).all()
