from sqlmodel import Session, create_engine, select

from lorecraft.content.news import (
    NewsValidationError,
    export_news_yaml,
    load_news_yaml,
    validate_news_document,
)
from lorecraft.db import create_tables
from lorecraft.models.news import NewsItem


def _engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def test_load_news_yaml_imports_valid_document(tmp_path) -> None:
    source = tmp_path / "news.yaml"
    source.write_text(
        """
format_version: "1.0"
announcements:
  - id: news-2026-07-02-welcome
    type: server
    title: "Welcome to Ashmoore"
    body: "A new quest line begins."
    published_at: 2026-07-02T12:00:00Z
    expires_at: 2026-08-02T12:00:00Z
    priority: normal
    tags: [quest-content]
""",
        encoding="utf-8",
    )
    engine = _engine()
    with Session(engine) as session:
        document = load_news_yaml(source, session)
        session.commit()
        assert len(document.announcements) == 1

        items = session.exec(select(NewsItem)).all()
        assert len(items) == 1
        assert items[0].id == "news-2026-07-02-welcome"
        assert items[0].title == "Welcome to Ashmoore"
        assert items[0].expires_at is not None


def test_validate_news_document_rejects_duplicate_ids() -> None:
    data = {
        "announcements": [
            {"id": "news-1", "title": "First"},
            {"id": "news-1", "title": "Duplicate"},
        ]
    }
    try:
        validate_news_document(data)
        raise AssertionError("expected NewsValidationError")
    except NewsValidationError:
        pass


def test_validate_news_document_rejects_expiry_before_publish() -> None:
    data = {
        "announcements": [
            {
                "id": "news-1",
                "title": "Bad dates",
                "published_at": "2026-07-02T12:00:00Z",
                "expires_at": "2026-07-01T12:00:00Z",
            }
        ]
    }
    try:
        validate_news_document(data)
        raise AssertionError("expected NewsValidationError")
    except NewsValidationError:
        pass


def test_export_news_yaml_round_trips(tmp_path) -> None:
    engine = _engine()
    with Session(engine) as session:
        session.add(
            NewsItem(
                id="news-001",
                type="bulletin",
                title="Exported news",
                published_at=1720000000.0,
                expires_at=None,
                tags=["a"],
            )
        )
        session.commit()

        out_path = tmp_path / "news.yaml"
        export_news_yaml(session, out_path)

    assert out_path.is_file()

    with Session(_engine()) as reimport_session:
        document = load_news_yaml(out_path, reimport_session)
        assert len(document.announcements) == 1
        assert document.announcements[0].id == "news-001"
