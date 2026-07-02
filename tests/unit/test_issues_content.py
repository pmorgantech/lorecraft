from sqlmodel import Session, create_engine, select

from lorecraft.content.issues import (
    IssuesValidationError,
    export_issues_yaml,
    load_issues_yaml,
    validate_issues_document,
)
from lorecraft.db import create_tables
from lorecraft.models.issue import Issue


def _engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def test_load_issues_yaml_imports_valid_document(tmp_path) -> None:
    source = tmp_path / "issues.yaml"
    source.write_text(
        """
format_version: "1.0"
issues:
  - id: issue-001
    type: bug
    title: "Movement race condition"
    status: open
    priority: high
    component: movement
    tags: [threading]
""",
        encoding="utf-8",
    )
    engine = _engine()
    with Session(engine) as session:
        document = load_issues_yaml(source, session)
        session.commit()
        assert len(document.issues) == 1

        issues = session.exec(select(Issue)).all()
        assert len(issues) == 1
        assert issues[0].id == "issue-001"
        assert issues[0].title == "Movement race condition"
        assert issues[0].tags == ["threading"]


def test_validate_issues_document_rejects_duplicate_ids() -> None:
    data = {
        "issues": [
            {"id": "issue-001", "title": "First"},
            {"id": "issue-001", "title": "Duplicate"},
        ]
    }
    try:
        validate_issues_document(data)
        raise AssertionError("expected IssuesValidationError")
    except IssuesValidationError:
        pass


def test_validate_issues_document_rejects_missing_link_target() -> None:
    data = {
        "issues": [
            {
                "id": "issue-001",
                "title": "First",
                "links": [{"type": "depends_on", "id": "issue-999"}],
            }
        ]
    }
    try:
        validate_issues_document(data)
        raise AssertionError("expected IssuesValidationError")
    except IssuesValidationError:
        pass


def test_export_issues_yaml_round_trips(tmp_path) -> None:
    engine = _engine()
    with Session(engine) as session:
        session.add(
            Issue(
                id="issue-001",
                type="bug",
                title="Exported issue",
                status="open",
                priority="normal",
                created_at=1720000000.0,
                updated_at=1720000000.0,
                tags=["a", "b"],
            )
        )
        session.commit()

        out_path = tmp_path / "issues.yaml"
        export_issues_yaml(session, out_path)

    assert out_path.is_file()

    with Session(_engine()) as reimport_session:
        document = load_issues_yaml(out_path, reimport_session)
        assert len(document.issues) == 1
        assert document.issues[0].id == "issue-001"
        assert document.issues[0].tags == ["a", "b"]
