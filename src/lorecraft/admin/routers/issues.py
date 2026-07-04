"""Admin API router for repo-tracked issue tracking."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from lorecraft.admin.auth import Moderator, Observer
from lorecraft.content.issues import create_issue as build_issue
from lorecraft.content.issues import export_issues_yaml
from lorecraft.content.paths import resolve_repo_path
from lorecraft.repos.issue_repo import IssueRepo

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


def _issue_dict(issue: Any) -> dict[str, Any]:
    return {
        "id": issue.id,
        "type": issue.type,
        "title": issue.title,
        "description": issue.description,
        "status": issue.status,
        "priority": issue.priority,
        "component": issue.component,
        "created_by": issue.created_by,
        "assigned_to": issue.assigned_to,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
        "tags": issue.tags,
        "links": issue.links,
    }


def _sync_yaml(state: Any, session: Session) -> None:
    export_issues_yaml(session, resolve_repo_path(state.settings.issues_yaml_path))


@router.get("/issues")
async def list_issues(
    request: Request,
    _: Observer,
    status: str | None = None,
    priority: str | None = None,
    component: str | None = None,
    type: str | None = None,
    assigned_to: str | None = None,
) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        issues = IssueRepo(session).list_filtered(
            status=status,
            priority=priority,
            component=component,
            type_=type,
            assigned_to=assigned_to,
        )
        return [_issue_dict(issue) for issue in issues]


@router.get("/issues/{issue_id}")
async def get_issue(issue_id: str, request: Request, _: Observer) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        issue = IssueRepo(session).get(issue_id)
        if issue is None:
            raise HTTPException(status_code=404, detail="Issue not found")
        return _issue_dict(issue)


class _CreateIssueBody(BaseModel):
    title: str
    type: str = "bug"
    description: str = ""
    status: str = "open"
    priority: str = "normal"
    component: str = ""
    assigned_to: str = ""
    tags: list[str] = []


@router.post("/issues")
async def create_issue(
    body: _CreateIssueBody, request: Request, token: Moderator
) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        issue = build_issue(
            session,
            title=body.title,
            type=body.type,
            description=body.description,
            status=body.status,
            priority=body.priority,
            component=body.component,
            created_by=token.username,
            assigned_to=body.assigned_to,
            tags=body.tags,
        )
        session.commit()
        session.refresh(issue)
        _sync_yaml(state, session)
        return _issue_dict(issue)


class _UpdateIssueBody(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    component: str | None = None
    assigned_to: str | None = None
    tags: list[str] | None = None


@router.put("/issues/{issue_id}")
async def update_issue(
    issue_id: str, body: _UpdateIssueBody, request: Request, _: Moderator
) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        repo = IssueRepo(session)
        issue = repo.get(issue_id)
        if issue is None:
            raise HTTPException(status_code=404, detail="Issue not found")
        if body.title is not None:
            issue.title = body.title
        if body.description is not None:
            issue.description = body.description
        if body.status is not None:
            issue.status = body.status
        if body.priority is not None:
            issue.priority = body.priority
        if body.component is not None:
            issue.component = body.component
        if body.assigned_to is not None:
            issue.assigned_to = body.assigned_to
        if body.tags is not None:
            issue.tags = body.tags
        issue.updated_at = time.time()
        session.add(issue)
        session.commit()
        session.refresh(issue)
        _sync_yaml(state, session)
        return _issue_dict(issue)
