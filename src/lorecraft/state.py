"""Shared application state dataclass (avoids circular imports)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import Engine

from lorecraft.admin.broadcaster import AdminBroadcaster
from lorecraft.clock.world_clock import WorldClockRunner
from lorecraft.config import Settings
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.engine import CommandEngine
from lorecraft.game.events import EventBus
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rules import RuleEngine


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
