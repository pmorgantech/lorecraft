"""Data access for repo-tracked help topics."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, col, func, select

from lorecraft.models.help import HelpTopic
from lorecraft.engine.repos.base import Repository


class HelpRepo(Repository[HelpTopic, int]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, HelpTopic)

    def all_topics(self) -> Sequence[HelpTopic]:
        """Every topic, ordered by numeric id (the listing order)."""
        return self.session.exec(select(HelpTopic).order_by(col(HelpTopic.id))).all()

    def by_name(self, name: str) -> HelpTopic | None:
        return self.session.exec(
            select(HelpTopic).where(func.lower(HelpTopic.name) == name.lower())
        ).first()

    def by_reference(self, ref: str) -> HelpTopic | None:
        """Resolve a topic by numeric id (`"3"`) or name (`"combat"`)."""
        ref = ref.strip()
        if ref.isdigit():
            return self.get(int(ref))
        return self.by_name(ref)

    def search(self, query: str) -> Sequence[HelpTopic]:
        """Topics whose name, title, or keywords contain ``query`` (case-insensitive).

        Ordered by id so results are stable and match the listing numbers.
        """
        q = query.strip().lower()
        if not q:
            return self.all_topics()
        like = f"%{q}%"
        # name/title via SQL LIKE; keywords (a JSON list) matched in Python since
        # SQLite JSON querying isn't portable across our supported setups.
        rows = self.session.exec(
            select(HelpTopic)
            .where(col(HelpTopic.name).ilike(like) | col(HelpTopic.title).ilike(like))
            .order_by(col(HelpTopic.id))
        ).all()
        matched: dict[int, HelpTopic] = {t.id: t for t in rows}
        for topic in self.all_topics():
            if any(q in kw.lower() for kw in topic.keywords):
                matched[topic.id] = topic
        return [matched[i] for i in sorted(matched)]
