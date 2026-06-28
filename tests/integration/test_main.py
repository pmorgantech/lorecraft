import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import anyio
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from lorecraft.config import Settings
from lorecraft.main import create_app
from lorecraft.models.audit import AuditEvent
from lorecraft.models.player import Player
from lorecraft.models.session import PlayerSession
from lorecraft.models.world import Room

AsgiMessage = dict[str, Any]
AsgiReceive = Callable[[], Awaitable[AsgiMessage]]
AsgiSend = Callable[[AsgiMessage], Awaitable[None]]


def test_health_endpoint_initializes_lifespan() -> None:
    anyio.run(_test_health_endpoint_initializes_lifespan)


async def _test_health_endpoint_initializes_lifespan() -> None:
    app = create_app(
        settings=Settings(database_path=":memory:", audit_database_path=":memory:")
    )

    async with _lifespan(app):
        messages = await _run_http_get(app, "/health")

    assert _json_response(messages) == {"status": "ok"}


def test_lifespan_seeds_starter_world_for_empty_database() -> None:
    anyio.run(_test_lifespan_seeds_starter_world_for_empty_database)


async def _test_lifespan_seeds_starter_world_for_empty_database() -> None:
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
    app = create_app(
        settings=Settings(database_path=":memory:", audit_database_path=":memory:"),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )

    async with _lifespan(app):
        with Session(game_engine) as session:
            player = session.get(Player, "player-1")
            rooms = session.exec(select(Room)).all()

    assert player is not None
    assert player.current_room_id == "tavern"
    assert {room.id for room in rooms} == {"square", "tavern"}


def test_web_client_assets_expose_minimal_browser_harness() -> None:
    anyio.run(_test_web_client_assets_expose_minimal_browser_harness)


async def _test_web_client_assets_expose_minimal_browser_harness() -> None:
    app = create_app(
        settings=Settings(database_path=":memory:", audit_database_path=":memory:")
    )

    async with _lifespan(app):
        index = _text_response(await _run_http_get(app, "/"))
        script = _text_response(await _run_http_get(app, "/static/app.js"))
        styles = _text_response(await _run_http_get(app, "/static/app.css"))

    assert 'id="connect-form"' in index
    assert 'id="command-form"' in index
    assert 'id="message-feed"' in index
    assert 'id="minimap"' in index
    assert 'id="inventory-list"' in index
    assert "@tailwindcss/browser@4" in index
    assert "function routeMessage" in script
    assert "function renderInventory" in script
    assert "function renderMap" in script
    assert "const state = {" in script
    assert "new WebSocket(websocketUrl(playerId))" in script
    assert "--bg-void" in styles
    assert ".map-room.is-fog" in styles
    assert ".message-feed" in styles


def test_websocket_connects_and_dispatches_text_commands() -> None:
    anyio.run(_test_websocket_connects_and_dispatches_text_commands)


async def _test_websocket_connects_and_dispatches_text_commands() -> None:
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
    app = create_app(
        settings=Settings(database_path=":memory:", audit_database_path=":memory:"),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )
    async with _lifespan(app):
        messages = await _run_websocket(
            app,
            query_string=b"player_id=player-1",
            incoming=[
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "text": "dance"},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )
    payloads = [
        json.loads(message["text"])
        for message in messages
        if message["type"] == "websocket.send"
    ]

    assert payloads[0]["type"] == "connected"
    assert payloads[0]["player_id"] == "player-1"
    assert payloads[0]["room_id"] == "tavern"
    assert payloads[0]["updates"]["room"]["id"] == "tavern"
    assert payloads[0]["updates"]["inventory"] == []
    assert payloads[1]["type"] == "command_result"
    assert payloads[1]["command"] == "dance"
    assert payloads[1]["verb"] == "dance"
    assert payloads[1]["noun"] is None
    assert payloads[1]["messages"] == ["I don't understand that command."]
    assert payloads[1]["room_messages"] == []
    assert payloads[1]["updates"]["room_id"] == "tavern"

    with Session(audit_engine) as session:
        audit_events = session.exec(select(AuditEvent)).all()

    blocked_events = [
        event for event in audit_events if event.event_type == "command_blocked"
    ]
    assert len(blocked_events) == 1
    assert blocked_events[0].severity == "WARNING"


def test_websocket_movement_persists_room_change() -> None:
    anyio.run(_test_websocket_movement_persists_room_change)


async def _test_websocket_movement_persists_room_change() -> None:
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
    app = create_app(
        settings=Settings(database_path=":memory:", audit_database_path=":memory:"),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )
    async with _lifespan(app):
        messages = await _run_websocket(
            app,
            query_string=b"player_id=player-1",
            incoming=[
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "text": "go east"},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )
    payloads = [
        json.loads(message["text"])
        for message in messages
        if message["type"] == "websocket.send"
    ]

    with Session(game_engine) as session:
        player = session.get(Player, "player-1")
    with Session(audit_engine) as session:
        audit_events = session.exec(select(AuditEvent)).all()

    assert payloads[1]["messages"] == ["You go east."]
    assert payloads[1]["updates"]["room_id"] == "square"
    assert payloads[1]["updates"]["room"]["id"] == "square"
    assert {room["id"] for room in payloads[1]["updates"]["visited_rooms"]} == {
        "square",
        "tavern",
    }
    assert player.current_room_id == "square"
    assert "command_executed" in [event.event_type for event in audit_events]


def test_websocket_inventory_pickup_persists_item() -> None:
    anyio.run(_test_websocket_inventory_pickup_persists_item)


async def _test_websocket_inventory_pickup_persists_item() -> None:
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
    app = create_app(
        settings=Settings(database_path=":memory:", audit_database_path=":memory:"),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )
    async with _lifespan(app):
        messages = await _run_websocket(
            app,
            query_string=b"player_id=player-1",
            incoming=[
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "text": "take old sword"},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )
    payloads = [
        json.loads(message["text"])
        for message in messages
        if message["type"] == "websocket.send"
    ]

    with Session(game_engine) as session:
        player = session.get(Player, "player-1")

    assert payloads[1]["messages"] == ["You take Old Sword."]
    assert payloads[1]["updates"]["inventory"] == [
        {
            "id": "old_sword",
            "name": "Old Sword",
            "description": "Nicked but serviceable.",
        }
    ]
    assert player is not None
    assert player.inventory == ["old_sword"]


def test_websocket_save_and_load_preserve_player_state() -> None:
    anyio.run(_test_websocket_save_and_load_preserve_player_state)


async def _test_websocket_save_and_load_preserve_player_state() -> None:
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
    app = create_app(
        settings=Settings(database_path=":memory:", audit_database_path=":memory:"),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )
    async with _lifespan(app):
        messages = await _run_websocket(
            app,
            query_string=b"player_id=player-1",
            incoming=[
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "text": "take old sword"},
                {"type": "websocket.receive", "text": "save slot1"},
                {"type": "websocket.receive", "text": "go east"},
                {"type": "websocket.receive", "text": "load slot1"},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )
    payloads = [
        json.loads(message["text"])
        for message in messages
        if message["type"] == "websocket.send"
    ]

    with Session(game_engine) as session:
        player = session.get(Player, "player-1")

    assert payloads[2]["messages"] == ["Saved to slot1."]
    assert payloads[4]["messages"] == ["Loaded slot1."]
    assert payloads[4]["updates"]["room_id"] == "tavern"
    assert payloads[4]["updates"]["inventory"][0]["id"] == "old_sword"
    assert player is not None
    assert player.current_room_id == "tavern"
    assert player.inventory == ["old_sword"]
    assert player.visited_rooms == ["tavern"]


def test_websocket_disconnect_enters_grace_and_reconnect_syncs() -> None:
    anyio.run(_test_websocket_disconnect_enters_grace_and_reconnect_syncs)


async def _test_websocket_disconnect_enters_grace_and_reconnect_syncs() -> None:
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
    app = create_app(
        settings=Settings(
            database_path=":memory:",
            audit_database_path=":memory:",
            disconnect_grace_seconds=60.0,
        ),
        game_engine=game_engine,
        audit_engine=audit_engine,
    )
    async with _lifespan(app):
        await _run_websocket(
            app,
            query_string=b"player_id=player-1",
            incoming=[
                {"type": "websocket.connect"},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )
        with Session(game_engine) as session:
            grace_session = session.exec(select(PlayerSession)).one()
            grace_session_id = grace_session.id
            assert grace_session.status == "grace"
            assert grace_session.grace_expires_at is not None

        messages = await _run_websocket(
            app,
            query_string=b"player_id=player-1",
            incoming=[
                {"type": "websocket.connect"},
                {"type": "websocket.disconnect", "code": 1000},
            ],
        )

    payloads = [
        json.loads(message["text"])
        for message in messages
        if message["type"] == "websocket.send"
    ]
    with Session(audit_engine) as session:
        audit_events = session.exec(select(AuditEvent)).all()

    assert payloads[0]["type"] == "connected"
    assert payloads[0]["session_id"] == grace_session_id
    assert payloads[0]["reconnected"] is True
    assert payloads[1]["type"] == "reconnect_sync"
    assert payloads[1]["updates"]["room_id"] == "tavern"
    assert "player_disconnected" in [event.event_type for event in audit_events]
    assert "player_reconnected" in [event.event_type for event in audit_events]


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
                "state": {},
            },
            receive,
            send,
        )
    return messages


async def _run_websocket(
    app: Any, *, query_string: bytes, incoming: list[AsgiMessage]
) -> list[AsgiMessage]:
    messages: list[AsgiMessage] = []
    receive_tx, receive_rx = anyio.create_memory_object_stream[AsgiMessage](16)

    async def receive() -> AsgiMessage:
        return await receive_rx.receive()

    async def send(message: AsgiMessage) -> None:
        messages.append(message)

    async with receive_tx, receive_rx:
        for message in incoming:
            await receive_tx.send(message)

        with anyio.fail_after(5):
            await app(
                {
                    "type": "websocket",
                    "asgi": {"version": "3.0", "spec_version": "2.4"},
                    "scheme": "ws",
                    "path": "/ws",
                    "raw_path": b"/ws",
                    "query_string": query_string,
                    "headers": [],
                    "client": ("testclient", 50000),
                    "server": ("testserver", 80),
                    "subprotocols": [],
                    "state": {},
                },
                receive,
                send,
            )
    return messages


def _json_response(messages: list[AsgiMessage]) -> dict[str, Any]:
    return json.loads(_text_response(messages))


def _text_response(messages: list[AsgiMessage]) -> str:
    assert messages[0]["type"] == "http.response.start"
    assert messages[0]["status"] == 200
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return body.decode()
