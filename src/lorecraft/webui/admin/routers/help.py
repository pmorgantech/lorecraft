"""Admin API router for repo-tracked help topics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from lorecraft.webui.admin.auth import Moderator, Observer
from lorecraft.content.help import export_help_yaml
from lorecraft.content.paths import resolve_repo_path
from lorecraft.models.help import HelpTopic
from lorecraft.repos.help_repo import HelpRepo

router = APIRouter(tags=["admin"])

_SLUG_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789-_")


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


def _topic_dict(topic: HelpTopic) -> dict[str, Any]:
    return {
        "id": topic.id,
        "name": topic.name,
        "title": topic.title,
        "body": topic.body,
        "category": topic.category,
        "keywords": topic.keywords,
    }


def _sync_yaml(state: Any, session: Session) -> None:
    export_help_yaml(session, resolve_repo_path(state.settings.help_yaml_path))


def _validate_name(name: str) -> str:
    slug = name.strip().lower()
    if not slug or any(c not in _SLUG_ALLOWED for c in slug):
        raise HTTPException(
            status_code=400,
            detail="name must be a slug (letters, digits, '-' or '_')",
        )
    return slug


@router.get("/help")
async def list_help(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        return [_topic_dict(t) for t in HelpRepo(session).all_topics()]


class _CreateHelpBody(BaseModel):
    name: str
    title: str
    body: str = ""
    category: str = ""
    keywords: list[str] = []
    id: int | None = None  # optional; auto-assigned (max+1) when omitted


@router.post("/help")
async def create_help(
    body: _CreateHelpBody, request: Request, _: Moderator
) -> dict[str, Any]:
    state = _state(request)
    slug = _validate_name(body.name)
    with Session(state.game_engine) as session:
        repo = HelpRepo(session)
        if repo.by_name(slug) is not None:
            raise HTTPException(status_code=409, detail=f"name {slug!r} already exists")

        existing = repo.all_topics()
        if body.id is not None:
            if body.id < 1:
                raise HTTPException(status_code=400, detail="id must be >= 1")
            if repo.get(body.id) is not None:
                raise HTTPException(
                    status_code=409, detail=f"id {body.id} already exists"
                )
            new_id = body.id
        else:
            new_id = (max((t.id for t in existing), default=0)) + 1

        topic = HelpTopic(
            id=new_id,
            name=slug,
            title=body.title,
            body=body.body,
            category=body.category,
            keywords=[k.lower() for k in body.keywords],
        )
        repo.add(topic)
        session.commit()
        session.refresh(topic)
        _sync_yaml(state, session)
        return _topic_dict(topic)


class _UpdateHelpBody(BaseModel):
    name: str | None = None
    title: str | None = None
    body: str | None = None
    category: str | None = None
    keywords: list[str] | None = None


@router.put("/help/{topic_id}")
async def update_help(
    topic_id: int, body: _UpdateHelpBody, request: Request, _: Moderator
) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        repo = HelpRepo(session)
        topic = repo.get(topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail="Help topic not found")
        if body.name is not None:
            slug = _validate_name(body.name)
            clash = repo.by_name(slug)
            if clash is not None and clash.id != topic_id:
                raise HTTPException(
                    status_code=409, detail=f"name {slug!r} already exists"
                )
            topic.name = slug
        if body.title is not None:
            topic.title = body.title
        if body.body is not None:
            topic.body = body.body
        if body.category is not None:
            topic.category = body.category
        if body.keywords is not None:
            topic.keywords = [k.lower() for k in body.keywords]
        session.add(topic)
        session.commit()
        session.refresh(topic)
        _sync_yaml(state, session)
        return _topic_dict(topic)


@router.delete("/help/{topic_id}")
async def delete_help(topic_id: int, request: Request, _: Moderator) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        repo = HelpRepo(session)
        topic = repo.get(topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail="Help topic not found")
        repo.delete(topic)
        session.commit()
        _sync_yaml(state, session)
        return {"id": topic_id, "status": "deleted"}
