"""Integration tests for the public, unauthenticated news API (JSON + RSS)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import anyio
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from lorecraft.config import Settings
from lorecraft.main import create_app
from lorecraft.models.news import NewsItem

_SETTINGS = Settings(
    database_path=":memory:",
    audit_database_path=":memory:",
    admin_jwt_secret="test-jwt-secret-for-news-api-tests!",
)

AsgiMessage = dict[str, Any]


def _make_engines() -> tuple[Any, Any]:
    from lorecraft.db import create_tables

    game = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    audit = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(game_engine=game, audit_engine=audit)
    return game, audit


@asynccontextmanager
async def _lifespan(app: Any) -> AsyncIterator[None]:
    recv_tx, recv_rx = anyio.create_memory_object_stream[AsgiMessage](4)
    send_tx, send_rx = anyio.create_memory_object_stream[AsgiMessage](4)
    async with recv_tx, recv_rx, send_tx, send_rx, anyio.create_task_group() as tg:
        tg.start_soon(
            app,
            {"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}},
            recv_rx.receive,
            send_tx.send,
        )
        await recv_tx.send({"type": "lifespan.startup"})
        startup = await send_rx.receive()
        assert startup == {"type": "lifespan.startup.complete"}
        try:
            yield
        finally:
            await recv_tx.send({"type": "lifespan.shutdown"})
            shutdown = await send_rx.receive()
            assert shutdown == {"type": "lifespan.shutdown.complete"}


async def _http_raw(app: Any, method: str, path: str) -> tuple[int, str, bytes]:
    """Return (status, content_type, raw body) without assuming JSON."""
    sent = False
    messages: list[AsgiMessage] = []

    async def receive() -> AsgiMessage:
        nonlocal sent
        if sent:
            await anyio.sleep_forever()
        sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg: AsgiMessage) -> None:
        messages.append(msg)

    with anyio.fail_after(5):
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "method": method.upper(),
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "state": {},
            },
            receive,
            send,
        )
    start = next(m for m in messages if m["type"] == "http.response.start")
    status = start["status"]
    content_type = next(
        (v.decode() for k, v in start["headers"] if k == b"content-type"), ""
    )
    body_bytes = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return status, content_type, body_bytes


def test_news_feed_returns_rss_xml_with_active_items() -> None:
    anyio.run(_test_news_feed)


async def _test_news_feed() -> None:
    game_engine, audit_engine = _make_engines()
    now = time.time()
    with Session(game_engine) as session:
        session.add(
            NewsItem(
                id="news-active",
                type="server",
                title="Welcome",
                body="Hello adventurer.",
                published_at=now - 10,
                expires_at=None,
            )
        )
        session.add(
            NewsItem(
                id="news-expired",
                type="maintenance",
                title="Old maintenance",
                published_at=now - 1000,
                expires_at=now - 10,
            )
        )
        session.commit()

    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, content_type, body = await _http_raw(app, "GET", "/api/news/feed")

    assert status == 200
    assert "rss" in content_type
    text = body.decode()
    assert "<rss" in text
    assert "Welcome" in text
    assert "Old maintenance" not in text


def test_news_json_excludes_expired_items() -> None:
    anyio.run(_test_news_json)


async def _test_news_json() -> None:
    game_engine, audit_engine = _make_engines()
    now = time.time()
    with Session(game_engine) as session:
        session.add(
            NewsItem(
                id="news-active",
                title="Active",
                published_at=now - 10,
                expires_at=None,
            )
        )
        session.add(
            NewsItem(
                id="news-expired",
                title="Expired",
                published_at=now - 1000,
                expires_at=now - 10,
            )
        )
        session.commit()

    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, _content_type, body = await _http_raw(app, "GET", "/api/news")

    assert status == 200
    import json

    data = json.loads(body)
    ids = {item["id"] for item in data}
    assert "news-active" in ids
    assert "news-expired" not in ids
