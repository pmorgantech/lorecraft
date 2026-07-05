"""Shared application state dataclass (avoids circular imports)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.engine import Engine

from lorecraft.admin.broadcaster import AdminBroadcaster
from lorecraft.clock.world_clock import WorldClockRunner
from lorecraft.config import Settings
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.services.container import ServiceContainer
from lorecraft.services.effects import EffectService
from lorecraft.services.meters import MeterService
from lorecraft.services.mobile_route import MobileRouteService
from lorecraft.services.scheduler import SchedulerService
from lorecraft.types import JsonObject


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
    admin_broadcaster: AdminBroadcaster
    scheduler: SchedulerService
    services: ServiceContainer
    rng: GameRng
    meters: MeterService
    effects: EffectService
    mobile_routes: MobileRouteService
    pending_disambig: dict[str, JsonObject] = field(default_factory=dict)
    # Single-use WebSocket connect tickets: ticket -> (player_id, expires_at
    # epoch seconds). In-memory only, matching pending_disambig — fine for
    # this engine's single-process deployment target. See web/auth.py.
    ws_tickets: dict[str, tuple[str, float]] = field(default_factory=dict)
