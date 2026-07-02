from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.models.issue import Issue
from lorecraft.repos.issue_repo import IssueRepo


def _engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def test_issue_repo_round_trip_and_filters() -> None:
    engine = _engine()
    with Session(engine) as session:
        repo = IssueRepo(session)
        repo.add(
            Issue(
                id="issue-001",
                type="bug",
                title="Movement race condition",
                status="open",
                priority="high",
                component="movement",
                created_at=1.0,
                updated_at=1.0,
            )
        )
        repo.add(
            Issue(
                id="issue-002",
                type="todo",
                title="Write more tests",
                status="resolved",
                priority="normal",
                component="tooling",
                created_at=2.0,
                updated_at=2.0,
            )
        )
        session.commit()

        assert repo.get("issue-001") is not None
        assert repo.get("missing") is None

        open_issues = repo.list_filtered(status="open")
        assert [i.id for i in open_issues] == ["issue-001"]

        movement_issues = repo.list_filtered(component="movement")
        assert [i.id for i in movement_issues] == ["issue-001"]

        all_issues = repo.list_filtered()
        assert {i.id for i in all_issues} == {"issue-001", "issue-002"}


def test_issue_repo_delete() -> None:
    engine = _engine()
    with Session(engine) as session:
        repo = IssueRepo(session)
        issue = repo.add(
            Issue(id="issue-001", title="Temp", created_at=1.0, updated_at=1.0)
        )
        session.commit()
        repo.delete(issue)
        session.commit()
        assert repo.get("issue-001") is None
