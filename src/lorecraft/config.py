"""Environment-driven engine configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_path: str = "game.db"
    audit_database_path: str = "audit.db"
    world_time_ratio: float = 60.0
    websocket_path: str = "/ws"


def load_settings() -> Settings:
    """Load settings from environment variables."""

    return Settings(
        database_path=os.getenv("LORECRAFT_DB_PATH", "game.db"),
        audit_database_path=os.getenv("LORECRAFT_AUDIT_DB_PATH", "audit.db"),
        world_time_ratio=float(os.getenv("LORECRAFT_WORLD_TIME_RATIO", "60.0")),
        websocket_path=os.getenv("LORECRAFT_WEBSOCKET_PATH", "/ws"),
    )
