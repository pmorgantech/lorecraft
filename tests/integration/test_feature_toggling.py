"""Feature enable/disable integration tests (tier split, step 12b).

Proves the manifest-gating wired through ``ServiceContainer.build`` and
``create_app(enabled_features=...)`` actually takes effect end to end: a disabled
Tier 2 feature's service is ``None`` and its verbs are absent from the live
``CommandRegistry``, while the app still boots and serves ``/health``. The
always-on Tier 1 ``save`` verb survives any feature set.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import anyio
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from lorecraft.config import Settings
from lorecraft.features.loader import discover_features
from lorecraft.main import create_app

AsgiMessage = dict[str, Any]


def _all_features_except(*disabled: str) -> list[str]:
    """Every discovered feature key except the named ones.

    ``enabled_features`` is a whitelist, so disabling one feature means listing
    all the others. Dependencies (equipment->traits, containers->item_components)
    stay satisfied as long as we only drop features nothing depends on.
    """
    return [key for key in discover_features() if key not in disabled]


def _make_app(enabled_features: list[str] | None) -> Any:
    game_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    audit_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return create_app(
        settings=Settings(database_path=":memory:", audit_database_path=":memory:"),
        game_engine=game_engine,
        audit_engine=audit_engine,
        enabled_features=enabled_features,
    )


def test_disabling_economy_removes_service_and_verbs() -> None:
    anyio.run(_test_disabling_economy_removes_service_and_verbs)


async def _test_disabling_economy_removes_service_and_verbs() -> None:
    app = _make_app(_all_features_except("economy"))
    async with _lifespan(app):
        state = app.state.lorecraft
        assert state.services.economy is None
        for verb in ("buy", "sell", "list", "appraise"):
            assert state.registry.get(verb) is None, (
                f"{verb!r} must be absent when economy is disabled"
            )
        # A neighbouring feature stays intact.
        assert state.services.inventory is not None


def test_disabling_transit_removes_verbs_and_app_still_boots() -> None:
    anyio.run(_test_disabling_transit_removes_verbs_and_app_still_boots)


async def _test_disabling_transit_removes_verbs_and_app_still_boots() -> None:
    app = _make_app(_all_features_except("transit"))
    async with _lifespan(app):
        state = app.state.lorecraft
        for verb in ("board", "disembark", "schedule"):
            assert state.registry.get(verb) is None, (
                f"{verb!r} must be absent when transit is disabled"
            )
        # App is still live and serving.
        messages = await _run_http_get(app, "/health")
        assert _json_response(messages) == {"status": "ok"}


def test_all_features_on_registers_gated_verbs() -> None:
    anyio.run(_test_all_features_on_registers_gated_verbs)


async def _test_all_features_on_registers_gated_verbs() -> None:
    # enabled_features=None -> "all on" (behaviour-preserving default).
    app = _make_app(None)
    async with _lifespan(app):
        state = app.state.lorecraft
        for verb in ("buy", "sell", "board", "deposit", "withdraw"):
            assert state.registry.get(verb) is not None, (
                f"{verb!r} must be present when all features are on"
            )
        assert state.services.economy is not None
        assert state.services.bank is not None


def test_empty_feature_set_keeps_engine_verbs_only() -> None:
    anyio.run(_test_empty_feature_set_keeps_engine_verbs_only)


async def _test_empty_feature_set_keeps_engine_verbs_only() -> None:
    app = _make_app([])
    async with _lifespan(app):
        state = app.state.lorecraft
        # Every Tier 2 service is gone.
        assert state.services.economy is None
        assert state.services.movement is None
        assert state.services.inventory is None
        assert state.services.quest is None
        # Tier 1 shell verbs survive an empty feature set.
        for verb in ("help", "save", "load", "quit"):
            assert state.registry.get(verb) is not None, (
                f"engine verb {verb!r} must survive an empty feature set"
            )
        # And the app still serves.
        messages = await _run_http_get(app, "/health")
        assert _json_response(messages) == {"status": "ok"}


# --- ASGI lifespan / request helpers (mirrors tests/integration/test_main.py) ---


@asynccontextmanager
async def _lifespan(app: Any) -> Any:
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


async def _run_http_get(app: Any, path: str) -> list[AsgiMessage]:
    sent = False
    messages: list[AsgiMessage] = []

    async def receive() -> AsgiMessage:
        nonlocal sent
        if sent:
            await anyio.sleep_forever()
        sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: AsgiMessage) -> None:
        messages.append(message)

    with anyio.fail_after(5):
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )
    return messages


def _json_response(messages: list[AsgiMessage]) -> Any:
    import json

    body = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return json.loads(body)
