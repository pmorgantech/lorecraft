"""Public, unauthenticated news endpoints: JSON API and RSS 2.0 feed."""

from __future__ import annotations

import time
from typing import Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlmodel import Session

from lorecraft.content.news import to_iso
from lorecraft.repos.news_repo import NewsRepo

router = APIRouter(tags=["news"])


def _news_dict(item: Any) -> dict[str, Any]:
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


@router.get("/api/news")
async def news_json(request: Request) -> list[dict[str, Any]]:
    state = request.app.state.lorecraft
    with Session(state.game_engine) as session:
        items = NewsRepo(session).list_active(now=time.time())
        return [_news_dict(item) for item in items]


@router.get("/api/news/feed")
async def news_feed(request: Request) -> Response:
    state = request.app.state.lorecraft
    with Session(state.game_engine) as session:
        items = NewsRepo(session).list_active(now=time.time())

    entries = "\n".join(
        f"""    <item>
      <title>{escape(item.title)}</title>
      <description>{escape(item.body)}</description>
      <pubDate>{to_iso(item.published_at)}</pubDate>
      <guid>{escape(item.id)}</guid>
    </item>"""
        for item in items
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Lorecraft News</title>
    <description>Announcements and events</description>
{entries}
  </channel>
</rss>"""
    return Response(content=xml, media_type="application/rss+xml")
