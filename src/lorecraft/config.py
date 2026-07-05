"""Environment-driven engine configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# Populate os.environ from a repo-root .env file (if present) before any
# Settings are read. Real env vars already set always take precedence.
load_dotenv()


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
    issues_yaml_path: str = "docs/issues.yaml"
    news_yaml_path: str = "docs/news.yaml"
    help_yaml_path: str = "docs/help_topics.yaml"
    seed_player_id: str = "player-1"
    seed_player_username: str = "player-1"
    seed_player_start_room: str = "village_square"
    # Player session JWT (persisted to .env if not set — see ensure_persisted_secret)
    player_session_secret: str = ""
    player_session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days
    # Player API access/refresh tokens (POST /auth/login, /auth/refresh); signed
    # with the same player_session_secret but a distinct token `type` so they
    # can never be replayed as the browser's `lorecraft_session` cookie or vice versa.
    player_access_token_ttl_seconds: int = 900  # 15 minutes
    player_refresh_token_ttl_seconds: int = 28800  # 8 hours
    # Single-use WebSocket ticket TTL (POST /auth/ws-ticket -> WS ?ticket=)
    player_ws_ticket_ttl_seconds: float = 60.0
    # Dev/back-compat fallback: trust ?player_id=/&pid= (HTTP) and the raw
    # /ws?player_id= handshake param (WebSocket) instead of a signed session
    # cookie / ws-ticket. Off by default since Sprint 4 (player auth) shipped
    # the real login + WS-ticket flow — the browser and JSON API no longer
    # need it. Test fixtures that intentionally connect directly (protocol-
    # level tests, not exercising the login UI) opt back in explicitly.
    allow_query_player_id: bool = False
    # Root logger level for lorecraft.observability.configure_logging()
    log_level: str = "INFO"
    # Seed for the app-wide GameRng (game/rng.py) — None means OS entropy.
    # Set to a fixed int for deterministic single-actor scripts (see
    # tests/simulation/test_audit_regression.py's determinism contract).
    rng_seed: int | None = None
    # Password complexity policy enforced when a *new* local account credential
    # is created (docs/wishlist.md — Player Creation). Not applied to logins of
    # existing accounts. Configurable via LORECRAFT_PASSWORD_* env vars.
    password_min_length: int = 8
    password_max_length: int = 32
    password_require_mixed_case: bool = True
    password_require_symbol: bool = False
    password_require_number: bool = True


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    return int(raw)


def load_settings() -> Settings:
    """Load settings from environment variables (and .env, via load_dotenv above)."""

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
        issues_yaml_path=os.getenv("LORECRAFT_ISSUES_YAML_PATH", "docs/issues.yaml"),
        news_yaml_path=os.getenv("LORECRAFT_NEWS_YAML_PATH", "docs/news.yaml"),
        help_yaml_path=os.getenv("LORECRAFT_HELP_YAML_PATH", "docs/help_topics.yaml"),
        seed_player_id=os.getenv("LORECRAFT_SEED_PLAYER_ID", "player-1"),
        seed_player_username=os.getenv("LORECRAFT_SEED_PLAYER_USERNAME", "player-1"),
        seed_player_start_room=os.getenv(
            "LORECRAFT_SEED_PLAYER_START_ROOM", "village_square"
        ),
        player_session_secret=os.getenv("LORECRAFT_PLAYER_SESSION_SECRET", ""),
        player_session_ttl_seconds=int(
            os.getenv("LORECRAFT_PLAYER_SESSION_TTL_SECONDS", str(60 * 60 * 24 * 7))
        ),
        player_access_token_ttl_seconds=int(
            os.getenv("LORECRAFT_PLAYER_ACCESS_TTL", "900")
        ),
        player_refresh_token_ttl_seconds=int(
            os.getenv("LORECRAFT_PLAYER_REFRESH_TTL", "28800")
        ),
        player_ws_ticket_ttl_seconds=float(
            os.getenv("LORECRAFT_PLAYER_WS_TICKET_TTL_SECONDS", "60.0")
        ),
        allow_query_player_id=_env_bool("LORECRAFT_ALLOW_QUERY_PLAYER_ID", True),
        log_level=os.getenv("LORECRAFT_LOG_LEVEL", "INFO"),
        rng_seed=_env_optional_int("LORECRAFT_RNG_SEED"),
        password_min_length=int(os.getenv("LORECRAFT_PASSWORD_MIN_LENGTH", "8")),
        password_max_length=int(os.getenv("LORECRAFT_PASSWORD_MAX_LENGTH", "32")),
        password_require_mixed_case=_env_bool(
            "LORECRAFT_PASSWORD_REQUIRE_MIXED_CASE", True
        ),
        password_require_symbol=_env_bool("LORECRAFT_PASSWORD_REQUIRE_SYMBOL", False),
        password_require_number=_env_bool("LORECRAFT_PASSWORD_REQUIRE_NUMBER", True),
    )


def ensure_persisted_secret(
    var_name: str, *, env_path: Path = Path(".env"), length: int = 32
) -> str:
    """Return the value of `var_name`, generating and persisting one to `.env` if unset.

    Unlike the ephemeral admin JWT secret fallback, this is meant for secrets that
    should survive process restarts (e.g. player session signing keys) without
    requiring the operator to set them manually. Only call this from a real
    server entrypoint — never from test setup — since it writes to disk.
    """
    existing = os.getenv(var_name)
    if existing:
        return existing

    value = secrets.token_hex(length)
    line = f"{var_name}={value}"
    if env_path.exists():
        content = env_path.read_text()
        if content and not content.endswith("\n"):
            content += "\n"
        env_path.write_text(content + line + "\n")
    else:
        env_path.write_text(line + "\n")
    os.environ[var_name] = value
    return value
