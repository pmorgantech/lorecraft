"""Database engine and table initialization helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

from lorecraft.config import Settings, load_settings
from lorecraft.models.audit import AuditEvent
from lorecraft.models.changeset import (
    Changeset,
    ChangesetItem,
    ConflictScanResult,
    WorldMigration,
)
from lorecraft.models.combat import CombatSession
from lorecraft.models.player import Player, PlayerStats, SaveSlot
from lorecraft.models.session import PlayerSession
from lorecraft.models.world import (
    Exit,
    Item,
    NPC,
    Room,
    RoomItem,
    WorldClock,
    WorldMeta,
)
from lorecraft.models.quest import PlayerQuestProgress, Quest
from lorecraft.models.interaction import PvpConsent, TradeOffer


GAME_TABLE_MODELS: tuple[type[SQLModel], ...] = (
    Room,
    Exit,
    Item,
    RoomItem,
    WorldMeta,
    Player,
    PlayerStats,
    PlayerSession,
    SaveSlot,
    WorldClock,
    NPC,
    Quest,
    PlayerQuestProgress,
    CombatSession,
    Changeset,
    ChangesetItem,
    WorldMigration,
    ConflictScanResult,
    TradeOffer,
    PvpConsent,
)

AUDIT_TABLE_MODELS: tuple[type[SQLModel], ...] = (AuditEvent,)


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


def create_game_engine(
    settings: Settings | None = None, *, echo: bool = False
) -> Engine:
    settings = settings or load_settings()
    return create_engine(database_url(settings.database_path), echo=echo)


def create_audit_engine(
    settings: Settings | None = None, *, echo: bool = False
) -> Engine:
    settings = settings or load_settings()
    return create_engine(database_url(settings.audit_database_path), echo=echo)


def create_tables(
    *,
    game_engine: Engine | None = None,
    audit_engine: Engine | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or load_settings()
    game_engine = game_engine or create_game_engine(settings)
    audit_engine = audit_engine or create_audit_engine(settings)

    _create_model_tables(game_engine, GAME_TABLE_MODELS)
    _create_model_tables(audit_engine, AUDIT_TABLE_MODELS)
    _ensure_sqlite_compat_columns(game_engine)


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
