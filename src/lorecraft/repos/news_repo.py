"""Data access for repo-tracked news and announcements."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, col, select

from lorecraft.models.news import NewsItem
from lorecraft.repos.base import Repository


class NewsRepo(Repository[NewsItem, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, NewsItem)

    def list_active(self, *, now: float) -> Sequence[NewsItem]:
        """Published items that haven't expired, newest first."""
        stmt = (
            select(NewsItem)
            .where(col(NewsItem.published_at) <= now)
            .where(
                (col(NewsItem.expires_at).is_(None)) | (col(NewsItem.expires_at) > now)
            )
            .order_by(col(NewsItem.published_at).desc())
        )
        return self.session.exec(stmt).all()
