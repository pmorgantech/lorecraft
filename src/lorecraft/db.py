"""Database engine and table initialization helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

from lorecraft.config import Settings, load_settings
from lorecraft.models.admin import AdminUser
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.models.bank import Bank, BankAccount
from lorecraft.models.changeset import (
    Changeset,
    ChangesetItem,
    ConflictScanResult,
    WorldMigration,
)
from lorecraft.models.combat import CombatSession
from lorecraft.models.dialogue import DialogueTree
from lorecraft.models.economy import RegionPricing, Shop, ShopStock
from lorecraft.models.issue import Issue
from lorecraft.engine.models.items import ItemInstance, ItemStack
from lorecraft.models.ledger import CoinBalance
from lorecraft.engine.models.meters import ActiveEffect, Meter
from lorecraft.engine.models.mobile import MobileRouteState
from lorecraft.models.news import NewsItem
from lorecraft.models.npc_memory import NpcMemory
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
from lorecraft.models.quest import PlayerQuestProgress, Quest
from lorecraft.models.interaction import PvpConsent, TradeOffer
from lorecraft.features.reputation.models import Reputation
from lorecraft.engine.models.scheduler import ScheduledJob
from lorecraft.models.transit import TransitLine, TransitStop


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
