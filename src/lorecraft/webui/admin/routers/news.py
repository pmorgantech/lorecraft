"""Admin API router for repo-tracked news and announcements."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, col, select

from lorecraft.webui.admin.auth import Moderator, Observer
from lorecraft.content.news import export_news_yaml
from lorecraft.content.paths import resolve_repo_path
from lorecraft.models.news import NewsItem
from lorecraft.repos.news_repo import NewsRepo

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


def _news_dict(item: NewsItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "type": item.type,
        "title": item.title,
        "body": item.body,
        "author": item.author,
        "published_at": item.published_at,
        "expires_at": item.expires_at,
        "priority": item.priority,
        "icon": item.icon,
        "tags": item.tags,
    }


def _sync_yaml(state: Any, session: Session) -> None:
    export_news_yaml(session, resolve_repo_path(state.settings.news_yaml_path))


@router.get("/news")
async def list_news(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        stmt = select(NewsItem).order_by(col(NewsItem.published_at).desc())
        items = session.exec(stmt).all()
        return [_news_dict(item) for item in items]


class _CreateNewsBody(BaseModel):
    title: str
    type: str = "bulletin"
    body: str = ""
    priority: str = "normal"
    icon: str = ""
    expires_at: float | None = None
    tags: list[str] = []


@router.post("/news")
async def create_news(
    body: _CreateNewsBody, request: Request, token: Moderator
) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        repo = NewsRepo(session)
        item = NewsItem(
            id=f"news-{uuid.uuid4().hex[:8]}",
            type=body.type,
            title=body.title,
            body=body.body,
            author=token.username,
            published_at=time.time(),
            expires_at=body.expires_at,
            priority=body.priority,
            icon=body.icon,
            tags=list(body.tags),
        )
        repo.add(item)
        session.commit()
        session.refresh(item)
        _sync_yaml(state, session)
        return _news_dict(item)


class _UpdateNewsBody(BaseModel):
    title: str | None = None
    body: str | None = None
    priority: str | None = None
    icon: str | None = None
    expires_at: float | None = None
    tags: list[str] | None = None


@router.put("/news/{news_id}")
async def update_news(
    news_id: str, body: _UpdateNewsBody, request: Request, _: Moderator
) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        repo = NewsRepo(session)
        item = repo.get(news_id)
        if item is None:
            raise HTTPException(status_code=404, detail="News item not found")
        if body.title is not None:
            item.title = body.title
        if body.body is not None:
            item.body = body.body
        if body.priority is not None:
            item.priority = body.priority
        if body.icon is not None:
            item.icon = body.icon
        if body.expires_at is not None:
            item.expires_at = body.expires_at
        if body.tags is not None:
            item.tags = body.tags
        session.add(item)
        session.commit()
        session.refresh(item)
        _sync_yaml(state, session)
        return _news_dict(item)


@router.delete("/news/{news_id}")
async def delete_news(news_id: str, request: Request, _: Moderator) -> dict[str, str]:
    state = _state(request)
    with Session(state.game_engine) as session:
        repo = NewsRepo(session)
        item = repo.get(news_id)
        if item is None:
            raise HTTPException(status_code=404, detail="News item not found")
        repo.delete(item)
        session.commit()
        _sync_yaml(state, session)
        return {"id": news_id, "status": "deleted"}
