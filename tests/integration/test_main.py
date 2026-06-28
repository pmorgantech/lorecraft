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
from lorecraft.models.world import Exit, Room

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
        with Session(game_engine) as session:
            session.add(
                Room(
                    id="tavern",
                    name="Tavern",
                    description="A warm room.",
                    map_x=0,
                    map_y=0,
                )
            )
            session.add(
                Player(
                    id="player-1",
                    username="petem",
                    current_room_id="tavern",
                    respawn_room_id="tavern",
                )
            )
            session.commit()

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
    assert payloads[1] == {
        "type": "command_result",
        "command": "dance",
        "verb": "dance",
        "noun": None,
        "messages": ["I don't understand that command."],
        "room_messages": [],
        "updates": {},
    }

    with Session(audit_engine) as session:
        audit_events = session.exec(select(AuditEvent)).all()

    assert len(audit_events) == 1
    assert audit_events[0].event_type == "command_blocked"
    assert audit_events[0].severity == "WARNING"


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
        with Session(game_engine) as session:
            session.add(
                Room(
                    id="tavern",
                    name="Tavern",
                    description="A warm room.",
                    map_x=0,
                    map_y=0,
                )
            )
            session.add(
                Room(
                    id="square",
                    name="Square",
                    description="A busy square.",
                    map_x=1,
                    map_y=0,
                )
            )
            session.add(
                Exit(room_id="tavern", direction="east", target_room_id="square")
            )
            session.add(
                Player(
                    id="player-1",
                    username="petem",
                    current_room_id="tavern",
                    respawn_room_id="tavern",
                )
            )
            session.commit()

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
    assert payloads[1]["updates"] == {"room_id": "square"}
    assert player.current_room_id == "square"
    assert audit_events[-1].event_type == "command_executed"


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
    assert messages[0]["type"] == "http.response.start"
    assert messages[0]["status"] == 200
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return json.loads(body)
