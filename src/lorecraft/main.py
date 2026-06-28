"""FastAPI service wiring for Lorecraft."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from lorecraft.clock.weather import register_weather_handlers
from lorecraft.clock.world_clock import WorldClockRunner
from lorecraft.commands import register_all_commands
from lorecraft.config import Settings, load_settings
from lorecraft.db import create_audit_engine, create_game_engine, create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.engine import CommandEngine
from lorecraft.game.events import EventBus
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rules import RuleEngine
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player
from lorecraft.models.world import Exit, Item, Room, RoomItem
from lorecraft.repos.audit_repo import AuditRepo
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.services.save import SessionSafetyService
from lorecraft.types import JsonObject, JsonValue

WEB_DIR = Path(__file__).parent / "web"
WEB_ASSETS = {
    "app.css": "text/css",
    "app.js": "text/javascript",
}


@dataclass
class AppState:
    settings: Settings
    game_engine: Engine
    audit_engine: Engine
    manager: ConnectionManager
    bus: EventBus
    registry: CommandRegistry
    rules: RuleEngine
    command_engine: CommandEngine
    clock_runner: WorldClockRunner


def create_app(
    *,
    settings: Settings | None = None,
    game_engine: Engine | None = None,
    audit_engine: Engine | None = None,
) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_game_engine = game_engine or create_game_engine(settings)
        resolved_audit_engine = audit_engine or create_audit_engine(settings)
        create_tables(
            game_engine=resolved_game_engine,
            audit_engine=resolved_audit_engine,
            settings=settings,
        )
        _ensure_starter_world(resolved_game_engine)
        manager = ConnectionManager()
        bus = EventBus()
        registry = CommandRegistry()
        rules = RuleEngine()
        clock_runner = WorldClockRunner(
            game_engine=resolved_game_engine,
            bus=bus,
            time_ratio=settings.world_time_ratio,
        )
        register_weather_handlers(bus, resolved_game_engine)
        state = AppState(
            settings=settings,
            game_engine=resolved_game_engine,
            audit_engine=resolved_audit_engine,
            manager=manager,
            bus=bus,
            registry=registry,
            rules=rules,
            command_engine=CommandEngine(registry, rules),
            clock_runner=clock_runner,
        )
        register_all_commands(state.registry)
        state.clock_runner.initialize()
        state.clock_runner.start()
        app.state.lorecraft = state
        try:
            yield
        finally:
            await state.clock_runner.stop()

    app = FastAPI(title="Lorecraft", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(_read_web_asset("index.html"))

    @app.get("/static/{asset_name}")
    async def static_asset(asset_name: str) -> Response:
        media_type = WEB_ASSETS.get(asset_name)
        if media_type is None:
            raise HTTPException(status_code=404)
        return Response(_read_web_asset(asset_name), media_type=media_type)

    @app.websocket(settings.websocket_path)
    async def websocket_endpoint(websocket: WebSocket) -> None:
        player_id = websocket.query_params.get("player_id")
        if not player_id:
            await websocket.close(code=1008, reason="player_id is required")
            return

        state = _get_state(websocket.app)

        with (
            Session(state.game_engine) as game_session,
            Session(state.audit_engine) as audit_session,
        ):
            player_repo = PlayerRepo(game_session)
            player = player_repo.get(player_id)
            if player is None:
                await websocket.close(code=1008, reason="unknown player")
                return
            room_repo = RoomRepo(game_session)
            item_repo = ItemRepo(game_session)
            room = room_repo.get(player.current_room_id)
            if room is None:
                await websocket.close(code=1011, reason="player room not found")
                return
            session_result = SessionSafetyService(
                game_session=game_session,
                audit_session=audit_session,
                bus=state.bus,
                grace_seconds=state.settings.disconnect_grace_seconds,
            ).start_or_resume_session(player)
            session_id = session_result.player_session.id
            updates = _player_ui_updates(player, room, room_repo, item_repo)
            connected_payload: JsonObject = {
                "type": "connected",
                "player_id": player_id,
                "room_id": room.id,
                "session_id": session_id,
                "reconnected": session_result.reconnected,
                "updates": updates,
            }
            reconnect_payload = (
                _reconnect_sync_payload(player, session_id, updates)
                if session_result.reconnected
                else None
            )
            room_id = room.id
            game_session.commit()
            audit_session.commit()

        await state.manager.connect(player_id, websocket, room_id=room_id)
        try:
            await websocket.send_json(connected_payload)
            if reconnect_payload is not None:
                await websocket.send_json(reconnect_payload)
            while True:
                command = await websocket.receive_text()
                response = _handle_websocket_command(
                    state, player_id, session_id, command
                )
                await websocket.send_json(response)
        except WebSocketDisconnect:
            with (
                Session(state.game_engine) as game_session,
                Session(state.audit_engine) as audit_session,
            ):
                player = PlayerRepo(game_session).get(player_id)
                if player is not None:
                    SessionSafetyService(
                        game_session=game_session,
                        audit_session=audit_session,
                        bus=state.bus,
                        grace_seconds=state.settings.disconnect_grace_seconds,
                    ).begin_grace_period(session_id, player)
                    game_session.commit()
                    audit_session.commit()
                    await state.manager.broadcast_to_room(
                        player.current_room_id,
                        {
                            "type": "room_event",
                            "messages": [f"{player.username}'s connection flickers."],
                        },
                        exclude=player.id,
                    )
            await state.manager.disconnect(player_id)

    return app


def _handle_websocket_command(
    state: AppState, player_id: str, session_id: str, command: str
) -> JsonObject:
    with (
        Session(state.game_engine) as game_session,
        Session(state.audit_engine) as audit_session,
    ):
        player_repo = PlayerRepo(game_session)
        room_repo = RoomRepo(game_session)
        player = player_repo.get(player_id)
        if player is None:
            return {
                "type": "error",
                "message": "Player no longer exists.",
            }
        room = room_repo.get(player.current_room_id)
        if room is None:
            return {
                "type": "error",
                "message": "Player room no longer exists.",
            }

        ctx = GameContext(
            player=player,
            room=room,
            clock=room_repo.world_clock(),
            player_repo=player_repo,
            room_repo=room_repo,
            item_repo=ItemRepo(game_session),
            npc_repo=NpcRepo(game_session),
            manager=state.manager,
            bus=state.bus,
            audit=AuditRepo(audit_session),
            transaction=TransactionContext.create(
                actor_id=player.id,
                correlation_id=session_id,
            ),
            session_id=session_id,
            commit_state=game_session.commit,
            commit_audit=audit_session.commit,
        )
        parsed = state.command_engine.handle_command(command, ctx)
        messages: list[JsonValue] = list(ctx.messages)
        room_messages: list[JsonValue] = list(ctx.room_messages)
        updates = {
            **ctx.updates,
            **_player_ui_updates(player, ctx.room, room_repo, ctx.item_repo),
        }
        response: JsonObject = {
            "type": "command_result",
            "command": parsed.raw,
            "verb": parsed.verb,
            "noun": parsed.noun,
            "messages": messages,
            "room_messages": room_messages,
            "updates": updates,
        }
        return response


def _get_state(app: FastAPI) -> AppState:
    state = app.state.lorecraft
    if not isinstance(state, AppState):
        raise RuntimeError("Lorecraft app state is not initialized.")
    return state


def _read_web_asset(asset_name: str) -> str:
    return (WEB_DIR / asset_name).read_text(encoding="utf-8")


def _reconnect_sync_payload(
    player: Player, session_id: str, updates: JsonObject
) -> JsonObject:
    return {
        "type": "reconnect_sync",
        "session_id": session_id,
        "player": {
            "id": player.id,
            "username": player.username,
            "current_room_id": player.current_room_id,
        },
        "room": updates["room"],
        "inventory": updates["inventory"],
        "time": updates["time"],
        "updates": updates,
    }


def _player_ui_updates(
    player: Player,
    room: Room,
    room_repo: RoomRepo,
    item_repo: ItemRepo,
) -> JsonObject:
    visited_rooms: list[JsonValue] = [
        _room_snapshot(visited_room, room_repo, visited_room_ids=player.visited_rooms)
        for visited_room in _visited_rooms(player, room_repo)
    ]
    return {
        "room_id": room.id,
        "room": _room_snapshot(room, room_repo, visited_room_ids=player.visited_rooms),
        "visited_rooms": visited_rooms,
        "inventory": _inventory_snapshot(player, item_repo),
        "time": _time_snapshot(room_repo),
    }


def _visited_rooms(player: Player, room_repo: RoomRepo) -> list[Room]:
    rooms: list[Room] = []
    for room_id in player.visited_rooms:
        room = room_repo.get(room_id)
        if room is not None:
            rooms.append(room)
    return rooms


def _room_snapshot(
    room: Room, room_repo: RoomRepo, *, visited_room_ids: list[str]
) -> JsonObject:
    exits: list[JsonValue] = []
    for exit_ in room_repo.exits(room.id):
        target_room = room_repo.get(exit_.target_room_id)
        target_payload: JsonObject = {
            "direction": exit_.direction,
            "target_room_id": exit_.target_room_id,
            "hidden": exit_.hidden,
            "locked": exit_.locked,
            "visited": exit_.target_room_id in visited_room_ids,
        }
        if target_room is not None:
            target_payload["target_map_x"] = target_room.map_x
            target_payload["target_map_y"] = target_room.map_y
        exits.append(target_payload)

    return {
        "id": room.id,
        "name": room.name,
        "description": room.description,
        "map_x": room.map_x,
        "map_y": room.map_y,
        "exits": exits,
    }


def _inventory_snapshot(player: Player, item_repo: ItemRepo) -> list[JsonValue]:
    items: list[JsonValue] = []
    for item_id in player.inventory:
        item = item_repo.get(item_id)
        if item is None:
            continue
        items.append(
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
            }
        )
    return items


def _time_snapshot(room_repo: RoomRepo) -> JsonObject:
    clock = room_repo.world_clock()
    if clock is None:
        return {}
    return {
        "hour": clock.current_hour,
        "minute": clock.current_minute,
        "day": clock.current_day,
        "season": clock.current_season,
        "weather": clock.weather,
    }


def _ensure_starter_world(game_engine: Engine) -> None:
    with Session(game_engine) as session:
        has_rooms = session.exec(select(Room)).first() is not None
        if not has_rooms:
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

        if session.get(Player, "player-1") is None:
            session.add(
                Player(
                    id="player-1",
                    username="player-1",
                    current_room_id="tavern",
                    respawn_room_id="tavern",
                    visited_rooms=["tavern"],
                )
            )
        if session.get(Item, "old_sword") is None:
            session.add(
                Item(
                    id="old_sword",
                    name="Old Sword",
                    description="Nicked but serviceable.",
                )
            )
        sword_in_room = session.exec(
            select(RoomItem).where(
                RoomItem.room_id == "tavern",
                RoomItem.item_id == "old_sword",
            )
        ).first()
        if sword_in_room is None:
            session.add(RoomItem(room_id="tavern", item_id="old_sword"))
        session.commit()


app = create_app()
