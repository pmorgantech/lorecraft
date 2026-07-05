"""Unit tests for help-topic content sync + repo (help system, Part 2)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.content.help import (
    HelpValidationError,
    ensure_help_bootstrapped,
    export_help_yaml,
    import_help,
    validate_help_document,
)
from lorecraft.db import create_tables
from lorecraft.repos.help_repo import HelpRepo

_DOC = {
    "format_version": "1.0",
    "topics": [
        {
            "id": 1,
            "name": "getting-started",
            "title": "Getting Started",
            "category": "Basics",
            "keywords": ["intro", "newbie"],
            "body": "welcome",
        },
        {
            "id": 2,
            "name": "combat",
            "title": "Fighting",
            "category": "World",
            "keywords": ["attack", "fight"],
            "body": "how to fight",
        },
    ],
}


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as s:
        yield s


class TestValidation:
    def test_valid_document(self) -> None:
        doc = validate_help_document(_DOC)
        assert len(doc.topics) == 2

    def test_duplicate_ids_rejected(self) -> None:
        bad = {
            "topics": [
                {"id": 1, "name": "a", "title": "A"},
                {"id": 1, "name": "b", "title": "B"},
            ]
        }
        with pytest.raises(HelpValidationError, match="duplicate help topic ids"):
            validate_help_document(bad)

    def test_duplicate_names_rejected(self) -> None:
        bad = {
            "topics": [
                {"id": 1, "name": "dup", "title": "A"},
                {"id": 2, "name": "DUP", "title": "B"},
            ]
        }
        with pytest.raises(HelpValidationError, match="duplicate help topic names"):
            validate_help_document(bad)

    def test_bad_slug_rejected(self) -> None:
        bad = {"topics": [{"id": 1, "name": "has spaces", "title": "A"}]}
        with pytest.raises(HelpValidationError, match="must be a slug"):
            validate_help_document(bad)

    def test_zero_id_rejected(self) -> None:
        bad = {"topics": [{"id": 0, "name": "a", "title": "A"}]}
        with pytest.raises(HelpValidationError, match="id must be >= 1"):
            validate_help_document(bad)


class TestRepo:
    def _load(self, session: Session) -> HelpRepo:
        import_help(validate_help_document(_DOC), session)
        session.commit()
        return HelpRepo(session)

    def test_by_reference_numeric_and_name(self, session: Session) -> None:
        repo = self._load(session)
        assert repo.by_reference("1").name == "getting-started"
        assert repo.by_reference("combat").id == 2
        # Case-insensitive name.
        assert repo.by_reference("COMBAT").id == 2
        assert repo.by_reference("99") is None
        assert repo.by_reference("nope") is None

    def test_all_topics_ordered_by_id(self, session: Session) -> None:
        repo = self._load(session)
        ids = [t.id for t in repo.all_topics()]
        assert ids == [1, 2]

    def test_search_matches_title_name_keywords(self, session: Session) -> None:
        repo = self._load(session)
        # Title match.
        assert [t.id for t in repo.search("fighting")] == [2]
        # Keyword match ("attack" is a keyword of topic 2, not in its title).
        assert [t.id for t in repo.search("attack")] == [2]
        # Name match.
        assert [t.id for t in repo.search("getting")] == [1]
        # Empty query returns everything.
        assert len(repo.search("")) == 2


class TestBootstrap:
    def test_bootstrap_imports_real_seed_yaml(self, session: Session) -> None:
        # The shipped docs/help_topics.yaml must load cleanly.
        ensure_help_bootstrapped(session, "docs/help_topics.yaml")
        session.commit()
        topics = HelpRepo(session).all_topics()
        assert len(topics) >= 5
        assert any(t.name == "getting-started" for t in topics)

    def test_bootstrap_is_idempotent(self, session: Session) -> None:
        ensure_help_bootstrapped(session, "docs/help_topics.yaml")
        session.commit()
        n = len(HelpRepo(session).all_topics())
        ensure_help_bootstrapped(session, "docs/help_topics.yaml")
        session.commit()
        assert len(HelpRepo(session).all_topics()) == n


class TestExportRoundTrip:
    def test_export_reimport(self, session: Session, tmp_path) -> None:
        import_help(validate_help_document(_DOC), session)
        session.commit()
        path = tmp_path / "help.yaml"
        export_help_yaml(session, path)

        # Fresh DB, re-import the exported file.
        engine2 = create_engine("sqlite://")
        create_tables(game_engine=engine2, audit_engine=create_engine("sqlite://"))
        with Session(engine2) as s2:
            ensure_help_bootstrapped(s2, str(path))
            s2.commit()
            names = {t.name for t in HelpRepo(s2).all_topics()}
        assert names == {"getting-started", "combat"}
