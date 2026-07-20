"""Shared fixtures/helpers for the split ``test_frontend_*`` characterization modules.

Leading underscore keeps pytest from collecting this as a test module (matching the
``tests/e2e/_helpers.py`` convention already used in this repo).

Most tests across these modules construct `Settings(..., allow_query_player_id=True)` — a
deliberate opt-in to the legacy `?player_id=`/cookie fallback (off by default since Sprint 4's
login/WS-ticket flow shipped; see docs/project/roadmap.md 4.6), since these tests exercise state
resolution directly rather than the login UI.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlencode

import anyio
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from lorecraft.db import create_tables

AsgiMessage = dict[str, Any]


def _make_engines() -> tuple[Any, Any]:
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
    receive_tx, receive_rx = anyio.create_memory_object_stream[AsgiMessage](4)
    send_tx, send_rx = anyio.create_memory_object_stream[AsgiMessage](4)

    async with (
        receive_tx,
        receive_rx,
        send_tx,
        send_rx,
        anyio.create_task_group() as tg,
    ):
        tg.start_soon(
            app,
            {
                "type": "lifespan",
                "asgi": {"version": "3.0", "spec_version": "2.0"},
                "state": {},
            },
            receive_rx.receive,
            send_tx.send,
        )
        await receive_tx.send({"type": "lifespan.startup"})
        startup = await send_rx.receive()
        assert startup == {"type": "lifespan.startup.complete"}
        try:
            yield
        finally:
            await receive_tx.send({"type": "lifespan.shutdown"})
            shutdown = await send_rx.receive()
            assert shutdown == {"type": "lifespan.shutdown.complete"}


async def _http_get(
    app: Any,
    path: str,
    *,
    cookies: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Run HTTP GET request and return (status, body)."""
    sent = False
    messages: list[AsgiMessage] = []

    query_string = b""
    if query_params:
        query_string = urlencode(query_params).encode()

    async def receive() -> AsgiMessage:
        nonlocal sent
        if sent:
            await anyio.sleep_forever()
        sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg: AsgiMessage) -> None:
        messages.append(msg)

    headers: list[tuple[bytes, bytes]] = []
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode()))

    with anyio.fail_after(5):
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": query_string,
                "headers": headers,
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "state": {},
            },
            receive,
            send,
        )

    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body_bytes = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return status, body_bytes.decode()


async def _http_post_form(
    app: Any,
    path: str,
    *,
    form: dict[str, str],
    cookies: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Run HTTP POST form request and return (status, body)."""
    sent = False
    messages: list[AsgiMessage] = []
    body = urlencode(form).encode()

    async def receive() -> AsgiMessage:
        nonlocal sent
        if sent:
            await anyio.sleep_forever()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(msg: AsgiMessage) -> None:
        messages.append(msg)

    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/x-www-form-urlencoded"),
        (b"content-length", str(len(body)).encode()),
    ]
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode()))

    with anyio.fail_after(5):
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "method": "POST",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": headers,
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "state": {},
            },
            receive,
            send,
        )

    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body_bytes = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return status, body_bytes.decode()
