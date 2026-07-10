"""FastAPI service wiring for Lorecraft."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from lorecraft.webui.admin.api import admin_router
from lorecraft.webui.admin.auth import hash_password
from lorecraft.webui.admin.broadcaster import AdminBroadcaster
from lorecraft.webui.admin.websocket import admin_ws_endpoint
from lorecraft.webui.player import create_web_host, load_feature_presentations
from lorecraft.features.weather.handlers import register_weather_handlers
from lorecraft.features.celestial.content import (
    register_tide_gate_handlers,
    sync_tide_gates,
)
from lorecraft.features.celestial.handlers import register_celestial_handlers
from lorecraft.engine.clock.celestial import moon_phase_for_day, tide_for_hour
from lorecraft.engine.clock.world_clock import WorldClockRunner
from lorecraft.commands import register_all_commands
from lorecraft.features import (
    discover_features,
    load_features,
    resolve_enabled_features,
    wire_features,
)
from lorecraft.content.issues import ensure_issues_bootstrapped
from lorecraft.content.news import ensure_news_bootstrapped
from lorecraft.content.help import ensure_help_bootstrapped
from lorecraft.features.npc.scheduler import NpcScheduler
from lorecraft.features.spawns.service import SpawnControllerService
from lorecraft.features.weather.fronts import (
    WeatherFrontService,
    register_storm_effects,
)
from lorecraft.scripting_wiring import build_trigger_service, load_yaml_config
from lorecraft.services.container import ServiceContainer
from lorecraft.engine.services.crash_reports import record_crash
from lorecraft.engine.services.scheduler import SchedulerService
from lorecraft.config import Settings, load_settings
from lorecraft.db import create_audit_engine, create_game_engine, create_tables
from lorecraft.engine.game.broadcast import broadcast_command_effects
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import build_game_context
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.meters import MeterDef
from lorecraft.engine.game.meters import get_registry as get_meter_registry
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.features.items.rules import register_item_rules
from lorecraft.models.admin import AdminUser
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import NPC, Room
from lorecraft.observability import bind_transaction_context, configure_logging
from lorecraft.world.bootstrap import ensure_world_bootstrapped
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.light.service import LightFuelService
from lorecraft.features.economy.restock import RestockService
from lorecraft.features.npc_ai.service import NpcBehaviorService
from lorecraft.features.quests.timer import QuestTimerService
from lorecraft.engine.services.mobile_route import MobileRouteService
from lorecraft.features.transit.service import TransitService
from lorecraft.engine.services.save import SessionSafetyService
from lorecraft.state import AppState
from lorecraft.types import JsonObject, JsonValue
from lorecraft.webui.player.auth import consume_ws_ticket
from lorecraft.webui.player.auth import router as player_auth_router
from lorecraft.webui.player.frontend import router as web_router
from lorecraft.webui.player.news_api import router as news_api_router

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "webui" / "player"
WEB_ASSETS = {
    "app.css": "text/css",
    "app.js": "text/javascript",
}
ADMIN_WEB_DIR = Path(__file__).parent / "webui" / "admin"


def create_app(
    *,
    settings: Settings | None = None,
    game_engine: Engine | None = None,
    audit_engine: Engine | None = None,
    enabled_features: Sequence[str] | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)

    # Warn if no JWT secret; generate an ephemeral one so the server still starts.
    effective_jwt_secret = settings.admin_jwt_secret
    if not effective_jwt_secret:
        effective_jwt_secret = secrets.token_hex(32)
        log.warning(
            "LORECRAFT_ADMIN_JWT_SECRET is not set. "
            "Using an ephemeral random secret — admin tokens will not survive restarts."
        )
    # Expose the (possibly generated) secret via settings-like object without mutation.
    # Copy every setting through, overriding only the (possibly generated) admin
    # JWT secret. `replace` (vs a field-by-field rebuild) means new Settings
    # fields are forwarded automatically instead of being silently dropped.
    resolved_settings = replace(settings, admin_jwt_secret=effective_jwt_secret)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_game_engine = game_engine or create_game_engine(resolved_settings)
        resolved_audit_engine = audit_engine or create_audit_engine(resolved_settings)
        create_tables(
            game_engine=resolved_game_engine,
            audit_engine=resolved_audit_engine,
            settings=resolved_settings,
        )
        ensure_world_bootstrapped(resolved_game_engine, resolved_settings)
        _ensure_admin_seed(resolved_game_engine, resolved_settings)
        with Session(resolved_game_engine) as issues_session:
            ensure_issues_bootstrapped(
                issues_session, resolved_settings.issues_yaml_path
            )
            issues_session.commit()
        with Session(resolved_game_engine) as news_session:
            ensure_news_bootstrapped(news_session, resolved_settings.news_yaml_path)
            news_session.commit()
        with Session(resolved_game_engine) as help_session:
            ensure_help_bootstrapped(help_session, resolved_settings.help_yaml_path)
            help_session.commit()

        manager = ConnectionManager()
        bus = EventBus()
        registry = CommandRegistry()
        rules = RuleEngine()
        register_item_rules(rules)
        admin_broadcaster = AdminBroadcaster()
        app_rng = GameRng(resolved_settings.rng_seed)
        clock_runner = WorldClockRunner(
            game_engine=resolved_game_engine,
            bus=bus,
            time_ratio=resolved_settings.world_time_ratio,
        )
        register_weather_handlers(bus, resolved_game_engine, rng=app_rng)
        register_celestial_handlers(bus)
        _load_celestial_content(resolved_settings.celestial_yaml_path)
        register_tide_gate_handlers(bus, resolved_game_engine)
        NpcScheduler(resolved_game_engine).register(bus)
        scheduler = SchedulerService(resolved_game_engine, app_rng)
        scheduler.register(bus)
        get_meter_registry().register(MeterDef(key="hp", base_maximum=_hp_base_maximum))
        meter_service = MeterService(resolved_game_engine, app_rng)
        meter_service.register(bus)
        effect_service = EffectService(resolved_game_engine, app_rng)
        effect_service.register(bus)
        mobile_route_service = MobileRouteService(resolved_game_engine, scheduler)
        mobile_route_service.register(bus)

        # Resolve the enabled Tier 2 feature set up front so services can be
        # built conditionally (docs/tier_split_refactor.md). Discovery imports
        # feature packages so their manifests self-register; the enabled set
        # (explicit arg > LORECRAFT_FEATURES > all discovered) is validated and
        # dependency-ordered. Default is "all on", so behaviour is unchanged.
        available_features = discover_features()
        enabled_feature_keys = resolve_enabled_features(
            enabled_features, available_features.keys()
        )
        loaded_features = load_features(enabled_feature_keys, available_features)
        enabled_set = set(loaded_features)
        if loaded_features:
            log.info("Enabled features: %s", ", ".join(loaded_features))

        # Feature-owned schedulable services: built and bus-registered only when
        # their owning Tier 2 feature is enabled. Unlike the ServiceContainer
        # services these hold the live engine/manager, so they live here rather
        # than in the (no-arg) container. Tier 1 services above (scheduler,
        # meters, effects, mobile_route) are always on.
        light_fuel_service = None
        if "light" in enabled_set:
            light_fuel_service = LightFuelService(resolved_game_engine)
            light_fuel_service.register(bus)
        restock_service = None
        if "economy" in enabled_set:
            restock_service = RestockService(resolved_game_engine)
            restock_service.register(bus)
        quest_timer_service = None
        if "quests" in enabled_set:
            quest_timer_service = QuestTimerService(resolved_game_engine, manager)
            quest_timer_service.register(bus)
        npc_behavior_service = None
        if "npc_ai" in enabled_set:
            npc_behavior_service = NpcBehaviorService(
                resolved_game_engine, manager, app_rng, meter_service, effect_service
            )
            npc_behavior_service.register(bus)
        weather_front_service = None
        if "weather" in enabled_set:
            register_storm_effects()
            weather_front_service = WeatherFrontService(
                resolved_game_engine,
                manager,
                app_rng,
                effect_service,
                load_yaml_config(resolved_settings.weather_fronts_yaml_path),
            )
            weather_front_service.register(bus)
        spawn_controller_service = None
        if "spawns" in enabled_set:
            spawn_controller_service = SpawnControllerService(
                resolved_game_engine,
                app_rng,
                load_yaml_config(resolved_settings.spawns_yaml_path),
            )
            spawn_controller_service.register(bus)
        transit_service = None
        if "transit" in enabled_set:
            transit_service = TransitService(
                resolved_game_engine, mobile_route_service, manager
            )
            transit_service.load_lines()

        services = ServiceContainer.build(enabled=enabled_set)
        if services.quest is not None:
            services.quest.register(bus)
        if services.fatigue is not None:
            services.fatigue.register(bus)
        if services.follow is not None:
            services.follow.register(bus)
        if services.hunts is not None:
            _load_hunt_definitions(resolved_settings.hunts_yaml_path)
            services.hunts.register(bus)
        if services.marks is not None:
            _load_mark_definitions(resolved_settings.marks_yaml_path)
            services.marks.register(bus)
        if "context_commands" in enabled_set:
            _load_context_commands(resolved_game_engine)

        # Scripting engine (A2): bind declarative on/when/do triggers loaded from world
        # content to the live bus. Runs after features register so their conditions/effects
        # are available; fail-closed on a malformed trigger.
        with Session(resolved_game_engine) as trigger_session:
            build_trigger_service(trigger_session, bus)

        # Forward key bus events to admin broadcaster
        def _push_player_moved(event: Event, ctx: object) -> None:
            admin_broadcaster.push(
                {
                    "type": "player_moved",
                    "player_id": str(event.payload.get("player_id", "")),
                    "from_room": str(event.payload.get("from_room_id", "")),
                    "to_room": str(event.payload.get("to_room_id", "")),
                }
            )

        def _push_player_disconnected(event: Event, ctx: object) -> None:
            admin_broadcaster.push(
                {
                    "type": "player_disconnected",
                    "player_id": str(event.payload.get("player_id", "")),
                    "status": "grace",
                }
            )

        def _push_player_reconnected(event: Event, ctx: object) -> None:
            admin_broadcaster.push(
                {
                    "type": "player_connected",
                    "player_id": str(event.payload.get("player_id", "")),
                    "username": str(event.payload.get("username", "")),
                    "room_id": str(event.payload.get("room_id", "")),
                }
            )

        def _push_clock_tick(event: Event, ctx: object) -> None:
            payload = event.payload
            admin_broadcaster.push(
                {
                    "type": "clock_tick",
                    "current_epoch": float(payload.get("current_epoch", 0.0)),  # type: ignore[arg-type]
                }
            )

        def _schedule_clock_broadcast(event: Event, ctx: object) -> None:
            """Schedule clock broadcast to players on TIME_ADVANCED."""

            async def broadcast_task() -> None:
                with Session(resolved_game_engine) as session:
                    clock = RoomRepo(session).world_clock()
                    if clock is not None:
                        await manager.broadcast_global(
                            {
                                "type": "time_update",
                                "hour": clock.current_hour,
                                "minute": clock.current_minute,
                                "day": clock.current_day,
                                "season": clock.current_season,
                                "weather": clock.weather,
                                "moon": moon_phase_for_day(clock.current_day),
                                "tide": tide_for_hour(clock.current_hour),
                            }
                        )

            try:
                asyncio.create_task(broadcast_task())
            except RuntimeError:
                pass  # No running event loop (e.g., in tests)

        def _push_issue_filed(event: Event, ctx: object) -> None:
            # An in-game `report` filed an issue via the content path (not the
            # admin API), so mirror the admin routers' content_changed push so
            # any open Issues tab live-refreshes. Same message shape the routers
            # emit via notify_content_changed.
            admin_broadcaster.push({"type": "content_changed", "resource": "issues"})

        def _push_command_executed(event: Event, ctx: object) -> None:
            # Live audit feed: every executed command records an audit row, so
            # nudge admin clients to refresh the Audit tab in real time (they
            # re-query with their current filters). The engine emits
            # COMMAND_EXECUTED on the bus after committing the audit row.
            payload = event.payload
            admin_broadcaster.push(
                {
                    "type": "audit_appended",
                    "actor_id": str(payload.get("actor_id", "")),
                    "summary": str(payload.get("summary", "")),
                    "room_id": str(payload.get("room_id", "")),
                }
            )

        bus.on(GameEvent.PLAYER_MOVED, _push_player_moved)
        bus.on(GameEvent.PLAYER_DISCONNECTED, _push_player_disconnected)
        bus.on(GameEvent.PLAYER_RECONNECTED, _push_player_reconnected)
        bus.on(GameEvent.TIME_ADVANCED, _push_clock_tick)
        bus.on(GameEvent.TIME_ADVANCED, _schedule_clock_broadcast)
        bus.on(GameEvent.ISSUE_FILED, _push_issue_filed)
        bus.on(GameEvent.COMMAND_EXECUTED, _push_command_executed)

        # Initialize WebHost and load feature presentations (step 11 of tier-split
        # refactor). Features with optional presentation.py modules can contribute
        # UI panels, static mounts, and scripts. This runs once at app startup,
        # never in headless modes (tests, simulation, CLI).
        web_host = create_web_host()
        load_feature_presentations(web_host, available_features)

        state = AppState(
            settings=resolved_settings,
            game_engine=resolved_game_engine,
            audit_engine=resolved_audit_engine,
            manager=manager,
            bus=bus,
            registry=registry,
            rules=rules,
            command_engine=CommandEngine(registry, rules),
            clock_runner=clock_runner,
            admin_broadcaster=admin_broadcaster,
            scheduler=scheduler,
            services=services,
            rng=app_rng,
            meters=meter_service,
            effects=effect_service,
            mobile_routes=mobile_route_service,
            web_host=web_host,
        )
        register_all_commands(state.registry, state.services, transit=transit_service)

        # Wire each enabled feature onto `state` (its register_fn registers the
        # feature's conditions/side effects/modifiers/etc. on the shared
        # registries). The enabled set was resolved above; command registration
        # for feature-gated services is handled inside register_all_commands.
        wire_features(state, loaded_features)

        state.clock_runner.initialize()
        # Tide gates must match the tide the world wakes to, not the last
        # transition (Sprint 54.3) — one sync now the clock row exists.
        with Session(resolved_game_engine) as _sync_session:
            _clock = RoomRepo(_sync_session).world_clock()
            if _clock is not None and sync_tide_gates(
                _sync_session, _clock.current_hour
            ):
                _sync_session.commit()
        state.clock_runner.start()
        app.state.lorecraft = state
        try:
            yield
        finally:
            await state.clock_runner.stop()

    app = FastAPI(title="Lorecraft", lifespan=lifespan)
    app.include_router(admin_router, prefix="/admin")

    # New HTMX + Jinja web UI (becomes the primary player UI)
    app.include_router(web_router)  # routes at /lobby, /game, /command, /partials/...
    app.include_router(news_api_router)  # public /api/news, /api/news/feed
    app.include_router(
        player_auth_router
    )  # /auth/login, /auth/refresh, /auth/ws-ticket

    # Mount new static tree (css/ js/ under /static)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=RedirectResponse)
    async def root_redirect():
        """New UI is now primary. Old vanilla client still available at /old if needed."""
        return RedirectResponse("/lobby", status_code=302)

    # Legacy flat static assets (kept for any direct references / old client)
    @app.get("/static/{asset_name}")
    async def static_asset(asset_name: str) -> Response:
        media_type = WEB_ASSETS.get(asset_name)
        if media_type is None:
            # Fall through to mounted static if present in subdirs
            raise HTTPException(status_code=404)
        return Response(_read_web_asset(asset_name), media_type=media_type)

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_index() -> HTMLResponse:
        html_path = ADMIN_WEB_DIR / "index.html"
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.websocket("/admin/ws")
    async def admin_websocket(websocket: WebSocket) -> None:
        state = _get_state(websocket.app)
        await admin_ws_endpoint(websocket, state)

    @app.websocket(resolved_settings.websocket_path)
    async def websocket_endpoint(websocket: WebSocket) -> None:
        state = _get_state(websocket.app)

        player_id = _resolve_ws_player_id(websocket, state)
        if player_id is None:
            await websocket.close(code=1008, reason="Invalid or expired ticket")
            return

        # Enforce a single live connection per player. A second browser/tab
        # logging in as an already-connected player is rejected here rather
        # than silently booting the first: the old behaviour (boot the DB
        # session + overwrite the connection slot) left the first tab's socket
        # orphaned but open, and the client's auto-reconnect turned it into a
        # boot war between the two tabs — the "HERE NOW out of sync" symptom.
        # Legitimate reconnection after a real drop is unaffected: the dropped
        # socket is already gone from the manager (see the WebSocketDisconnect
        # handler's manager.disconnect), so is_connected is False and the grace
        # period resume path below runs instead.
        if state.manager.is_connected(player_id):
            await websocket.accept()
            await websocket.close(code=1008, reason="already_connected")
            return

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
            safety_service = SessionSafetyService(
                game_session=game_session,
                audit_session=audit_session,
                bus=state.bus,
                grace_seconds=state.settings.disconnect_grace_seconds,
            )
            safety_service.boot_active_session(player_id)
            session_result = safety_service.start_or_resume_session(player)
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
            player_username = player.username
            room_id = room.id
            game_session.commit()
            audit_session.commit()

        state.admin_broadcaster.push(
            {
                "type": "player_connected",
                "player_id": player_id,
                "username": player_username,
                "room_id": room_id,
            }
        )
        await state.manager.connect(player_id, websocket, room_id=room_id)
        try:
            await state.manager.broadcast_to_room(
                room_id,
                {
                    "type": "player_joined",
                    "player_id": player_id,
                    "username": player_username,
                },
                exclude=player_id,
            )
            await websocket.send_json(connected_payload)
            if reconnect_payload is not None:
                await websocket.send_json(reconnect_payload)
            while True:
                command = await websocket.receive_text()
                response = await _handle_websocket_command(
                    state, player_id, session_id, command
                )
                await websocket.send_json(response)
        except WebSocketDisconnect:
            # Distinguish an involuntary drop from a graceful quit. A graceful
            # quit (POST /command with disconnect=True) has already torn this
            # session down: it began the grace period, broadcast "leaves the
            # game." + player_left, broke follows, and removed the socket from
            # the manager. In that case the socket is already gone, so bail out
            # — otherwise the room would see "connection flickers." on top of
            # "leaves the game.", grace would be re-begun, and player_left would
            # fire twice. Only a genuine drop (socket still live in the manager)
            # runs the flicker/grace/player_left/follow-break teardown here.
            if not state.manager.is_connected(player_id):
                return
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
                            "type": "feed_append",
                            "content": f"{player.username}'s connection flickers.",
                            "message_type": MessageType.ROOM_EVENT.value,
                        },
                        exclude=player.id,
                    )
                    await state.manager.broadcast_to_room(
                        player.current_room_id,
                        {
                            "type": "state_change",
                            "affected_panels": ["players-online"],
                            "actor_id": player.id,
                        },
                        exclude=player.id,
                    )
                    # Terminate any follow involving the dropped player and tell
                    # the still-connected other side.
                    follow_service = state.services.follow
                    if follow_service is not None:
                        await follow_service.break_on_disconnect(
                            state.manager, PlayerRepo(game_session), player_id
                        )
            # Deregister the leaving socket *before* the player_left broadcast:
            # this broadcast has no `exclude`, so with the connection still in
            # the pool it would try to send to the just-closed socket — the
            # WebSocketDisconnect that used to escape as ASGI-level log noise
            # on every disconnect-during-broadcast.
            await state.manager.disconnect(player_id)
            await state.manager.broadcast_to_room(
                room_id,
                {
                    "type": "player_left",
                    "player_id": player_id,
                    "username": player_username,
                },
            )

    return app


async def _handle_websocket_command(
    state: AppState, player_id: str, session_id: str, command: str
) -> JsonObject:
    # Resolve a bare number as a disambiguation choice.
    stripped = command.strip()
    if stripped.isdigit():
        pending = state.pending_disambig.pop(player_id, None)
        if pending is not None:
            choices: list[str] = pending.get("choices", [])  # type: ignore[assignment]
            idx = int(stripped) - 1
            if 0 <= idx < len(choices):
                verb: str = pending.get("verb", "examine")  # type: ignore[assignment]
                command = f"{verb} {choices[idx]}"
            # If out of range, fall through to normal (unknown) command handling.

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
        pre_room_id = player.current_room_id

        # Frozen session check
        active_session = player_repo.player_session(session_id)
        if active_session is not None and active_session.status == "frozen":
            return {
                "type": "system",
                "text": "Your session is frozen. Contact an administrator.",
            }

        room = room_repo.get(player.current_room_id)
        if room is None:
            return {
                "type": "error",
                "message": "Player room no longer exists.",
            }

        transaction = TransactionContext.create(
            actor_id=player.id,
            correlation_id=session_id,
        )
        try:
            ctx = build_game_context(
                game_session,
                player,
                room,
                bus=state.bus,
                manager=state.manager,
                transaction=transaction,
                session_id=session_id,
                rng=state.rng,
                meters=state.meters,
                effects=state.effects,
                clock=room_repo.world_clock(),
                audit_session=audit_session,
                commit_state=game_session.commit,
                commit_audit=audit_session.commit,
                rollback_state=game_session.rollback,
            )
            with bind_transaction_context(
                transaction.transaction_id, transaction.correlation_id
            ):
                parsed = state.command_engine.handle_command(command, ctx)
            await broadcast_command_effects(state.manager, ctx, pre_room_id=pre_room_id)
            messages: list[JsonValue] = list(ctx.messages)
            room_messages: list[JsonValue] = list(ctx.room_messages)
            # Chat echoes carry their channel (Sprint 52) so clients can tag/color
            # per channel; older clients reading only `text` degrade gracefully.
            chat_messages: list[JsonValue] = [
                {"text": echo.text, "channel": echo.channel} for echo in ctx.chat_echoes
            ]

            # Capture and store any pending disambiguation; don't send to client.
            disambig = ctx.updates.pop("disambig_pending", None)
            if disambig is not None and isinstance(disambig, dict):
                state.pending_disambig[player_id] = disambig

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
                "chat_messages": chat_messages,
                "updates": updates,
            }
            return response
        except Exception as exc:
            # Sprint 57.3: anything that escapes the command pipeline itself
            # (as opposed to a handler exception, already caught and
            # reported gracefully inside CommandEngine) previously killed the
            # WebSocket outright. Capture it and degrade to an in-game error
            # instead of a raw disconnect.
            log.exception("unhandled_command_pipeline_exception")
            game_session.rollback()
            record_crash(
                audit_session,
                transaction_id=transaction.transaction_id,
                correlation_id=transaction.correlation_id,
                player_id=player.id,
                command_text=command,
                exc=exc,
            )
            return {
                "type": "error",
                "message": "Something went wrong processing that command. "
                "It has been logged for review.",
            }


def _load_hunt_definitions(hunts_yaml_path: str) -> None:
    """Load scavenger-hunt definitions (Sprint 48) into the in-memory registry
    at startup. A missing file is fine — it just means no hunts are defined."""
    from pathlib import Path

    from lorecraft.features.hunts.models import get_registry, load_hunts_yaml

    registry = get_registry()
    registry.clear()
    if not Path(hunts_yaml_path).exists():
        return
    try:
        registry.load_document(load_hunts_yaml(hunts_yaml_path))
    except Exception as exc:  # malformed hunt content shouldn't crash boot
        log.warning("failed to load hunts from %s: %s", hunts_yaml_path, exc)


def _load_celestial_content(celestial_yaml_path: str) -> None:
    """Load celestial content (Sprint 54: tide gates) into the in-memory
    registry at startup. A missing file is fine — no tide-gated exits."""
    from pathlib import Path

    from lorecraft.features.celestial.content import (
        get_content_registry,
        load_celestial_yaml,
    )

    registry = get_content_registry()
    registry.clear()
    if not Path(celestial_yaml_path).exists():
        return
    try:
        registry.load_document(load_celestial_yaml(celestial_yaml_path))
    except Exception as exc:  # malformed content shouldn't crash boot
        log.warning("failed to load celestial from %s: %s", celestial_yaml_path, exc)


def _load_mark_definitions(marks_yaml_path: str) -> None:
    """Load mark definitions (Sprint 53) into the in-memory registry at
    startup. A missing file is fine — it just means no marks are defined."""
    from pathlib import Path

    from lorecraft.features.marks.models import get_registry, load_marks_yaml

    registry = get_registry()
    registry.clear()
    if not Path(marks_yaml_path).exists():
        return
    try:
        registry.load_document(load_marks_yaml(marks_yaml_path))
    except Exception as exc:  # malformed mark content shouldn't crash boot
        log.warning("failed to load marks from %s: %s", marks_yaml_path, exc)


def _load_context_commands(game_engine: Engine) -> None:
    """Scan every item + NPC for `context_commands` (Sprint 55) into the
    in-memory registry at startup, after the world is bootstrapped. Runs before
    `register_all_commands` so the dispatcher sees the loaded verbs."""
    from lorecraft.features.context_commands.models import get_registry

    registry = get_registry()
    registry.clear()
    with Session(game_engine) as session:
        registry.load_from_session(session)


def _get_state(app: FastAPI) -> AppState:
    state = app.state.lorecraft
    if not isinstance(state, AppState):
        raise RuntimeError("Lorecraft app state is not initialized.")
    return state


def _resolve_ws_player_id(websocket: WebSocket, state: AppState) -> str | None:
    """Resolve the connecting player id from a `?ticket=` handshake ticket.

    A `?ticket=` param, if present, is authoritative: an invalid/expired/
    already-used ticket rejects the connection outright rather than falling
    back to `?player_id=` (that fallback would defeat the point of tickets —
    an attacker could just send a garbage ticket to bypass them). The legacy
    `?player_id=` param is only consulted when no ticket param was sent at
    all, and only when `Settings.allow_query_player_id` explicitly allows it
    (default off; see Sprint 4.6 in docs/roadmap.md).
    """
    ticket = websocket.query_params.get("ticket")
    if ticket:
        return consume_ws_ticket(state, ticket)

    if state.settings.allow_query_player_id:
        return websocket.query_params.get("player_id")

    return None


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
            target_payload["target_map_z"] = target_room.map_z
        exits.append(target_payload)

    return {
        "id": room.id,
        "name": room.name,
        "description": room.description,
        "map_x": room.map_x,
        "map_y": room.map_y,
        "map_z": room.map_z,
        "exits": exits,
    }


def _inventory_snapshot(player: Player, item_repo: ItemRepo) -> list[JsonValue]:
    items: list[JsonValue] = []
    for stack, item in item_repo.stacks_carried_by(player.id):
        items.append(
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "quantity": stack.quantity,
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
        "moon": moon_phase_for_day(clock.current_day),
        "tide": tide_for_hour(clock.current_hour),
    }


def _ensure_admin_seed(game_engine: Engine, settings: Settings) -> None:
    if not settings.admin_seed_username or not settings.admin_seed_password:
        return
    with Session(game_engine) as session:
        existing = session.exec(
            select(AdminUser).where(AdminUser.username == settings.admin_seed_username)
        ).first()
        if existing is None:
            session.add(
                AdminUser(
                    id=str(uuid.uuid4()),
                    username=settings.admin_seed_username,
                    password_hash=hash_password(settings.admin_seed_password),
                    role=settings.admin_seed_role,
                    created_at=time.time(),
                )
            )
            session.commit()
            log.info(
                "Seeded admin user %r with role %r",
                settings.admin_seed_username,
                settings.admin_seed_role,
            )


def _hp_base_maximum(entity_type: str, entity_id: str, session: Session) -> float:
    """base_maximum for the "hp" MeterDef — the proof-of-primitive registration
    (engine_core.md §3.3): reads the definitional PlayerStats.max_hp / NPC.max_hp."""
    if entity_type == "player":
        stats = session.get(PlayerStats, entity_id)
        return float(stats.max_hp) if stats is not None else 100.0
    if entity_type == "npc":
        npc = session.get(NPC, entity_id)
        return float(npc.max_hp) if npc is not None else 50.0
    return 1.0


app = create_app()
