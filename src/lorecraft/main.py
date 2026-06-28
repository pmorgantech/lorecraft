"""FastAPI service wiring for Lorecraft."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from sqlalchemy.engine import Engine
from sqlmodel import Session

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
from lorecraft.repos.audit_repo import AuditRepo
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.types import JsonObject, JsonValue


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
        state = AppState(
            settings=settings,
            game_engine=resolved_game_engine,
            audit_engine=resolved_audit_engine,
            manager=ConnectionManager(),
            bus=EventBus(),
            registry=CommandRegistry(),
            rules=RuleEngine(),
            command_engine=CommandEngine(CommandRegistry(), RuleEngine()),
        )
        register_all_commands(state.registry)
        state.command_engine = CommandEngine(state.registry, state.rules)
        app.state.lorecraft = state
        yield

    app = FastAPI(title="Lorecraft", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.websocket(settings.websocket_path)
    async def websocket_endpoint(websocket: WebSocket) -> None:
        player_id = websocket.query_params.get("player_id")
        if not player_id:
            await websocket.close(code=1008, reason="player_id is required")
            return

        state = _get_state(websocket.app)
        session_id = str(uuid4())

        with Session(state.game_engine) as game_session:
            player_repo = PlayerRepo(game_session)
            player = player_repo.get(player_id)
            if player is None:
                await websocket.close(code=1008, reason="unknown player")
                return
            room = RoomRepo(game_session).get(player.current_room_id)
            if room is None:
                await websocket.close(code=1011, reason="player room not found")
                return

        await state.manager.connect(player_id, websocket, room_id=room.id)
        try:
            await websocket.send_json(
                {
                    "type": "connected",
                    "player_id": player_id,
                    "room_id": room.id,
                    "session_id": session_id,
                }
            )
            while True:
                command = await websocket.receive_text()
                response = _handle_websocket_command(
                    state, player_id, session_id, command
                )
                await websocket.send_json(response)
        except WebSocketDisconnect:
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
        response: JsonObject = {
            "type": "command_result",
            "command": parsed.raw,
            "verb": parsed.verb,
            "noun": parsed.noun,
            "messages": messages,
            "room_messages": room_messages,
            "updates": ctx.updates,
        }
        return response


def _get_state(app: FastAPI) -> AppState:
    state = app.state.lorecraft
    if not isinstance(state, AppState):
        raise RuntimeError("Lorecraft app state is not initialized.")
    return state


app = create_app()
