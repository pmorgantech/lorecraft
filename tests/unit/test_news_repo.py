from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.models.news import NewsItem
from lorecraft.repos.news_repo import NewsRepo


def _engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def test_news_repo_list_active_excludes_unpublished_and_expired() -> None:
    engine = _engine()
    now = 1_000_000.0
    with Session(engine) as session:
        repo = NewsRepo(session)
        repo.add(
            NewsItem(
                id="news-active", title="Active", published_at=now - 10, expires_at=None
            )
        )
        repo.add(
            NewsItem(
                id="news-future",
                title="Not yet published",
                published_at=now + 10,
                expires_at=None,
            )
        )
        repo.add(
            NewsItem(
                id="news-expired",
                title="Expired",
                published_at=now - 100,
                expires_at=now - 10,
            )
        )
        repo.add(
            NewsItem(
                id="news-active-with-future-expiry",
                title="Active, expires later",
                published_at=now - 10,
                expires_at=now + 10,
            )
        )
        session.commit()

        active_ids = {item.id for item in repo.list_active(now=now)}
        assert active_ids == {"news-active", "news-active-with-future-expiry"}
