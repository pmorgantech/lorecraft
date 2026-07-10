"""Database engine and table initialization helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

from lorecraft.config import Settings, load_settings
from lorecraft.models.admin import AdminUser
from lorecraft.engine.models.audit import AuditEvent, CrashReport
from lorecraft.features.bank.models import Bank, BankAccount
from lorecraft.models.changeset import (
    Changeset,
    ChangesetItem,
    ConflictScanResult,
    WorldMigration,
)
from lorecraft.models.combat import CombatSession
from lorecraft.features.npc.models import DialogueTree
from lorecraft.features.economy.models import RegionPricing, Shop, ShopStock
from lorecraft.models.help import HelpTopic
from lorecraft.models.issue import Issue
from lorecraft.engine.models.items import ItemInstance, ItemStack
from lorecraft.engine.models.ledger import CoinBalance
from lorecraft.engine.models.meters import ActiveEffect, Meter
from lorecraft.engine.models.mobile import MobileRouteState
from lorecraft.models.news import NewsItem
from lorecraft.features.npc_memory.models import NpcMemory
from lorecraft.engine.models.player import Player, PlayerStats, SaveSlot
from lorecraft.engine.models.player_auth import PlayerAuth
from lorecraft.engine.models.session import PlayerSession
from lorecraft.engine.models.world import (
    Exit,
    Item,
    NPC,
    Room,
    WorldClock,
    WorldMeta,
)
from lorecraft.features.quests.models import PlayerQuestProgress, Quest
from lorecraft.features.trading.models import PvpConsent, TradeOffer
from lorecraft.features.reputation.models import Reputation
from lorecraft.engine.models.scheduler import ScheduledJob
from lorecraft.features.transit.models import TransitLine, TransitStop


GAME_TABLE_MODELS: tuple[type[SQLModel], ...] = (
    AdminUser,
    Room,
    Exit,
    Item,
    ItemInstance,
    ItemStack,
    WorldMeta,
    Player,
    PlayerAuth,
    PlayerStats,
    PlayerSession,
    SaveSlot,
    WorldClock,
    NPC,
    DialogueTree,
    Quest,
    PlayerQuestProgress,
    CombatSession,
    Changeset,
    ChangesetItem,
    WorldMigration,
    ConflictScanResult,
    TradeOffer,
    PvpConsent,
    ScheduledJob,
    Issue,
    NewsItem,
    HelpTopic,
    Meter,
    ActiveEffect,
    CoinBalance,
    MobileRouteState,
    Reputation,
    Shop,
    ShopStock,
    RegionPricing,
    Bank,
    BankAccount,
    TransitLine,
    TransitStop,
    NpcMemory,
)

AUDIT_TABLE_MODELS: tuple[type[SQLModel], ...] = (AuditEvent, CrashReport)


def database_url(database_path_or_url: str) -> str:
    if database_path_or_url == ":memory:":
        return "sqlite://"
    if "://" in database_path_or_url:
        return database_path_or_url
    if database_path_or_url.startswith("sqlite:"):
        return database_path_or_url
    if Path(database_path_or_url).is_absolute():
        return f"sqlite:///{database_path_or_url}"
    return f"sqlite:///{database_path_or_url}"


def sqlite_url(database_path: str) -> str:
    return database_url(database_path)


def _pool_kwargs(url: str, settings: Settings) -> dict[str, int]:
    """Connection-pool kwargs for `create_engine`, or empty for SQLite.

    SQLite is single-writer and its dialect uses a thread-local/static pool, so
    QueuePool's `pool_size`/`pool_recycle` don't apply (and can error on the
    in-memory `StaticPool`). Only a networked backend (Postgres/MySQL) — the
    many-concurrent-players deployment target — gets the tuned pool.
    """
    if url.startswith("sqlite"):
        return {}
    return {
        "pool_size": settings.db_pool_size,
        "pool_recycle": settings.db_pool_recycle,
    }


_VALID_SYNCHRONOUS = {"OFF", "NORMAL", "FULL", "EXTRA"}


def configure_sqlite_engine(engine: Engine, settings: Settings) -> Engine:
    """Attach a connect-listener setting WAL + synchronous pragmas on SQLite.

    A no-op for non-SQLite backends and harmless for `:memory:` (which ignores
    WAL). WAL makes each commit an append to the `-wal` file with fsync deferred
    to periodic checkpoints, instead of a full fsync per commit — the dominant
    cost the Sprint 37 benchmarks surfaced. `journal_mode` is persistent in the
    DB header (idempotent to re-set); `synchronous` is per-connection, so both
    are set on every new connection. Returns the engine for call chaining.
    """
    if engine.dialect.name != "sqlite":
        return engine
    synchronous = settings.db_sqlite_synchronous.upper()
    if synchronous not in _VALID_SYNCHRONOUS:
        raise ValueError(
            f"invalid db_sqlite_synchronous {settings.db_sqlite_synchronous!r}; "
            f"expected one of {sorted(_VALID_SYNCHRONOUS)}"
        )
    use_wal = settings.db_sqlite_wal

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            if use_wal:
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA synchronous={synchronous}")
        finally:
            cursor.close()

    return engine


def create_game_engine(
    settings: Settings | None = None, *, echo: bool = False
) -> Engine:
    settings = settings or load_settings()
    url = database_url(settings.database_path)
    engine = create_engine(url, echo=echo, **_pool_kwargs(url, settings))
    return configure_sqlite_engine(engine, settings)


def create_audit_engine(
    settings: Settings | None = None, *, echo: bool = False
) -> Engine:
    settings = settings or load_settings()
    url = database_url(settings.audit_database_path)
    engine = create_engine(url, echo=echo, **_pool_kwargs(url, settings))
    return configure_sqlite_engine(engine, settings)


def create_tables(
    *,
    game_engine: Engine | None = None,
    audit_engine: Engine | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or load_settings()
    game_engine = game_engine or create_game_engine(settings)
    audit_engine = audit_engine or create_audit_engine(settings)

    create_game_tables(game_engine)
    create_audit_tables(audit_engine)


def create_game_tables(engine: Engine) -> None:
    _create_model_tables(engine, GAME_TABLE_MODELS)
    _ensure_sqlite_compat_columns(engine)


def create_audit_tables(engine: Engine) -> None:
    _create_model_tables(engine, AUDIT_TABLE_MODELS)


def _create_model_tables(engine: Engine, models: Sequence[type[SQLModel]]) -> None:
    for model in models:
        table = getattr(model, "__table__")
        table.create(engine, checkfirst=True)


def _ensure_sqlite_compat_columns(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    columns = {column["name"] for column in inspect(engine).get_columns("saveslot")}
    if "visited_rooms" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE saveslot "
                    "ADD COLUMN visited_rooms JSON NOT NULL DEFAULT '[]'"
                )
            )
    if "discovered_items" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE saveslot "
                    "ADD COLUMN discovered_items JSON NOT NULL DEFAULT '[]'"
                )
            )

    # Player.discovered_items (Sprint 46) — additive; existing player rows
    # default to an empty discovery list rather than erroring on SELECT.
    player_columns = {
        column["name"] for column in inspect(engine).get_columns("player")
    }
    if "discovered_items" not in player_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE player "
                    "ADD COLUMN discovered_items JSON NOT NULL DEFAULT '[]'"
                )
            )

    item_columns = {column["name"] for column in inspect(engine).get_columns("item")}
    if "aliases" not in item_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE item ADD COLUMN aliases JSON NOT NULL DEFAULT '[]'")
            )

    if "mechanism_states" not in item_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE item "
                    "ADD COLUMN mechanism_states JSON NOT NULL DEFAULT '[]'"
                )
            )
    if "mechanism_side_effects" not in item_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE item "
                    "ADD COLUMN mechanism_side_effects JSON NOT NULL DEFAULT '{}'"
                )
            )
    if "combination_side_effects" not in item_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE item "
                    "ADD COLUMN combination_side_effects JSON NOT NULL DEFAULT '{}'"
                )
            )
    if "context_commands" not in item_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE item "
                    "ADD COLUMN context_commands JSON NOT NULL DEFAULT '{}'"
                )
            )

    room_columns = {column["name"] for column in inspect(engine).get_columns("room")}
    if "map_z" not in room_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE room ADD COLUMN map_z INTEGER NOT NULL DEFAULT 0")
            )

    if "npc" in inspect(engine).get_table_names():
        npc_columns = {column["name"] for column in inspect(engine).get_columns("npc")}
        if "context_commands" not in npc_columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE npc "
                        "ADD COLUMN context_commands JSON NOT NULL DEFAULT '{}'"
                    )
                )
        if "following_player_id" not in npc_columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE npc ADD COLUMN following_player_id TEXT")
                )

    if "playerquestprogress" in inspect(engine).get_table_names():
        quest_columns = {
            column["name"]
            for column in inspect(engine).get_columns("playerquestprogress")
        }
        if "stage_started_epoch" not in quest_columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE playerquestprogress "
                        "ADD COLUMN stage_started_epoch REAL"
                    )
                )
