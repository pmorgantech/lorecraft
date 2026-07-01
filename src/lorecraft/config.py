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
    disconnect_grace_seconds: float = 60.0
    # Admin JWT (ephemeral random secret used if not set — not suitable for production)
    admin_jwt_secret: str = ""
    admin_jwt_access_ttl: int = 900  # 15 minutes
    admin_jwt_refresh_ttl: int = 28800  # 8 hours
    # Optional seed admin account created on first startup
    admin_seed_username: str = ""
    admin_seed_password: str = ""
    admin_seed_role: str = "superadmin"
    world_yaml_path: str = "world_content/world.yaml"
    seed_player_id: str = "player-1"
    seed_player_username: str = "player-1"
    seed_player_start_room: str = "village_square"


def load_settings() -> Settings:
    """Load settings from environment variables."""

    return Settings(
        database_path=os.getenv("LORECRAFT_DB_PATH", "game.db"),
        audit_database_path=os.getenv("LORECRAFT_AUDIT_DB_PATH", "audit.db"),
        world_time_ratio=float(os.getenv("LORECRAFT_WORLD_TIME_RATIO", "60.0")),
        websocket_path=os.getenv("LORECRAFT_WEBSOCKET_PATH", "/ws"),
        disconnect_grace_seconds=float(
            os.getenv("LORECRAFT_DISCONNECT_GRACE_SECONDS", "60.0")
        ),
        admin_jwt_secret=os.getenv("LORECRAFT_ADMIN_JWT_SECRET", ""),
        admin_jwt_access_ttl=int(os.getenv("LORECRAFT_ADMIN_JWT_ACCESS_TTL", "900")),
        admin_jwt_refresh_ttl=int(
            os.getenv("LORECRAFT_ADMIN_JWT_REFRESH_TTL", "28800")
        ),
        admin_seed_username=os.getenv("LORECRAFT_ADMIN_SEED_USERNAME", "admin"),
        admin_seed_password=os.getenv("LORECRAFT_ADMIN_SEED_PASSWORD", "admin"),
        admin_seed_role=os.getenv("LORECRAFT_ADMIN_SEED_ROLE", "superadmin"),
        world_yaml_path=os.getenv(
            "LORECRAFT_WORLD_YAML_PATH", "world_content/world.yaml"
        ),
        seed_player_id=os.getenv("LORECRAFT_SEED_PLAYER_ID", "player-1"),
        seed_player_username=os.getenv("LORECRAFT_SEED_PLAYER_USERNAME", "player-1"),
        seed_player_start_room=os.getenv(
            "LORECRAFT_SEED_PLAYER_START_ROOM", "village_square"
        ),
    )
