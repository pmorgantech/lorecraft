"""Database engine and table initialization helpers.

The reflection-based additive-column auto-migration scanner below lives here
rather than under ``engine/`` deliberately: ``db.py`` is a **composition-layer**
module (it already imports ``lorecraft.features.*`` across ``GAME_TABLE_MODELS``),
not Tier 1 engine infra, so ``test_tier_boundaries.py`` does not gate it. The
scanner mechanism is *Tier-1 in character* — opinion-free reflection that knows
only *how* to diff-and-``ALTER``, never *what* a column means for any feature.

The one caveat is the ``_ROOM_AREA_ID_TO_ZONE`` fold-map used by the Sprint 71.2
``room.area_id`` data migration: it embeds Sprint 71.2 world-content literals
directly here. That is accepted as a **bounded, self-clearing, one-shot
historical migration constant** (it transforms *past* data to a *known* target
state — it is not runtime branching on room IDs) and is a deliberate, documented
exception, not clean Tier 1. Once ``area_id`` is dropped it becomes dead code.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic_core import PydanticUndefined
from sqlalchemy import Column, Table, bindparam, event, inspect, text
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
from lorecraft.features.progression.models import ProgressionConfig
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
    ProgressionConfig,
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

logger = logging.getLogger(__name__)

# Sprint 71.2 fold: every legacy ``Room.area_id`` value → the 4-value ``zone``.
# Read verbatim from docs/roadmap.md §71.2 (the canonical fold table). Ashmoore's
# three kinds collapse to one zone; connectors fold to the zone they lead toward.
# Bounded, one-shot historical migration constant (see module docstring).
_ROOM_AREA_ID_TO_ZONE: Mapping[str, str] = {
    "town": "ashmoore",
    "wilderness": "ashmoore",
    "cave": "ashmoore",
    "cogsworth": "cogsworth",
    "whisperwood": "whisperwood",
    "port_veridian": "port_veridian",
    "old_trade_road": "cogsworth",
    "forest_road": "whisperwood",
    "river_bend": "port_veridian",
}

# ``room_type`` is mechanically derivable only for the three Ashmoore kinds
# (§71.2: the other zones' room_type was per-room authoring, not derivable).
_ROOM_TYPE_DERIVABLE_AREA_IDS: frozenset[str] = frozenset(
    {"town", "wilderness", "cave"}
)


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
    # Generic additive-column auto-migration (Sprint 75.1) — brings a legacy DB
    # missing any additive model column up to schema without hand-written shims.
    _ensure_additive_columns(engine)
    # Deliberate Sprint 71.2 room data migration (Sprint 75.3). Runs *after* the
    # additive pass, which will already have added room.zone / room.room_type as
    # empty nullable columns to fold the legacy area_id into.
    _migrate_room_area_id(engine)


def create_audit_tables(engine: Engine) -> None:
    _create_model_tables(engine, AUDIT_TABLE_MODELS)


def _create_model_tables(engine: Engine, models: Sequence[type[SQLModel]]) -> None:
    for model in models:
        table = getattr(model, "__table__")
        table.create(engine, checkfirst=True)


def _sql_default_literal(value: object) -> str:
    """Render a Python default value as a SQLite ``DEFAULT`` clause literal.

    Containers (list/dict, i.e. JSON columns) are ``json.dumps``-ed so a list
    factory yields ``'[]'`` and a dict factory ``'{}'``. ``bool`` is checked
    before ``int`` (it is a subclass) so ``False``/``True`` render as ``0``/``1``.
    """
    if isinstance(value, (list, dict)):
        return f"'{json.dumps(value)}'"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    # No other scalar default types occur in the game models; be explicit.
    raise TypeError(f"unsupported default value type for SQL literal: {value!r}")


def _type_zero_literal(column: Column[Any]) -> str:
    """Fallback ``DEFAULT`` for a NOT NULL column that declares no field default.

    ``ALTER TABLE … ADD COLUMN`` of a ``NOT NULL`` column on a non-empty table
    requires a default; without a declared one we fall back to the type's zero
    value (empty string / 0 / 0.0 / 0-as-false) so the ADD succeeds.
    """
    try:
        python_type = column.type.python_type
    except (NotImplementedError, AttributeError):
        return "''"
    if python_type is str:
        return "''"
    if python_type is bool:
        return "0"
    if python_type is int:
        return "0"
    if python_type is float:
        return "0.0"
    return "''"


def _field_default_literal(model: type[SQLModel], column: Column[Any]) -> str | None:
    """The SQL ``DEFAULT`` literal derived from a model's pydantic field default.

    Load-bearing (Sprint 75 design): the default must come from the *actual*
    field default, not a naive type-zero table, or string-typed defaults like
    ``item.quality = 'common'`` / ``room.terrain = 'normal'`` would silently
    become ``''`` on every legacy upgrade. Returns ``None`` when the field has no
    concrete default (nullable-with-no-default columns get no ``DEFAULT``).
    """
    field = model.model_fields.get(column.name)
    if field is None:
        return None
    if field.default_factory is not None:
        return _sql_default_literal(field.default_factory())  # type: ignore[call-arg]
    if field.default is not PydanticUndefined and field.default is not None:
        return _sql_default_literal(field.default)
    return None


def _ensure_additive_columns(engine: Engine) -> None:
    """Generic reflection-based additive-column auto-migration (Sprint 75.1).

    For every model in ``GAME_TABLE_MODELS`` diff the model's authoritative
    columns against the live reflected columns and reconcile strictly additively:

    - **model − live → ``ADD COLUMN``**, with a type from
      ``col.type.compile(dialect=…)`` and a ``DEFAULT`` derived from the actual
      pydantic field default (see ``_field_default_literal``). A missing column
      that is part of the **primary key** is *skipped with a WARNING* — SQLite
      cannot ``ADD`` a PK column via ``ALTER`` (this is exactly
      ``regionpricing.zone``, handed to ``_migrate_regionpricing_area_id``).
    - **live − model → WARN, never drop/alter** — the strictly-additive
      contract; a DB-only column is the rename/drop signal handled deliberately
      by the 75.3 / 75.4 migrations, out of scope for the generic scanner.

    A no-op on non-SQLite backends.
    """
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    live_tables = set(inspector.get_table_names())

    for model in GAME_TABLE_MODELS:
        table: Table = getattr(model, "__table__")
        table_name = table.name
        if table_name not in live_tables:
            # Brand-new DBs already got the full schema from _create_model_tables.
            continue

        live_columns = {col["name"] for col in inspector.get_columns(table_name)}
        model_columns = {col.name for col in table.columns}

        for column in table.columns:
            if column.name in live_columns:
                continue
            if column.primary_key:
                logger.warning(
                    "additive-migration: skipping missing PK column %s.%s "
                    "(cannot ADD a PRIMARY KEY column via ALTER; handled by a "
                    "dedicated table-rebuild migration if applicable)",
                    table_name,
                    column.name,
                )
                continue
            _add_column(engine, model, table_name, column)

        # Strictly-additive contract: report, never remove, live-only columns.
        for orphan in sorted(live_columns - model_columns):
            logger.warning(
                "additive-migration: DB column %s.%s is absent from the model; "
                "leaving it untouched (strictly-additive contract — drops/renames "
                "are handled by dedicated migrations, never the generic scanner)",
                table_name,
                orphan,
            )


def _add_column(
    engine: Engine, model: type[SQLModel], table_name: str, column: Column[Any]
) -> None:
    """Issue a single ``ALTER TABLE … ADD COLUMN`` for a model-declared column."""
    type_str = column.type.compile(dialect=engine.dialect)
    default_literal = _field_default_literal(model, column)
    if default_literal is None and not column.nullable:
        default_literal = _type_zero_literal(column)

    clause = f'"{column.name}" {type_str}'
    if not column.nullable:
        clause += " NOT NULL"
    if default_literal is not None:
        clause += f" DEFAULT {default_literal}"

    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {clause}"))
    logger.info("additive-migration: added column %s.%s", table_name, column.name)


def _migrate_room_area_id(engine: Engine) -> None:
    """Fold the legacy ``room.area_id`` into ``zone`` / ``room_type`` (Sprint 75.3).

    Runs after ``_ensure_additive_columns`` (which will already have added
    ``room.zone`` / ``room.room_type`` as empty nullable columns). If the legacy
    ``area_id`` column is still present, fold it into ``zone`` verbatim per the
    §71.2 table, derive ``room_type`` only for the three Ashmoore kinds (the other
    zones' room_type was per-room authoring, not derivable), then **DROP**
    ``area_id`` so the migration is self-clearing and idempotent — a second run
    finds no ``area_id`` and no-ops. In-place (no rebuild): ``area_id`` is a
    plain nullable, non-PK, non-indexed column.

    Warranted despite rooms being reseed-derived because admin ``POST``/``PUT``
    on rooms can produce admin-authored rows not in ``world.yaml`` that a reseed
    would never fix.
    """
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "room" not in inspector.get_table_names():
        return
    room_columns = {col["name"] for col in inspector.get_columns("room")}
    if "area_id" not in room_columns:
        return  # already migrated (or a fresh zone/room_type schema)

    with engine.begin() as connection:
        for area_id, zone in _ROOM_AREA_ID_TO_ZONE.items():
            connection.execute(
                text(
                    "UPDATE room SET zone = :zone "
                    "WHERE area_id = :area_id AND zone IS NULL"
                ),
                {"zone": zone, "area_id": area_id},
            )
        # room_type derivable only for the three Ashmoore kinds (§71.2).
        connection.execute(
            text(
                "UPDATE room SET room_type = area_id "
                "WHERE area_id IN :kinds AND room_type IS NULL"
            ).bindparams(
                bindparam(
                    "kinds",
                    tuple(sorted(_ROOM_TYPE_DERIVABLE_AREA_IDS)),
                    expanding=True,
                )
            )
        )
        # Drop the now-orphaned legacy column (SQLite ≥3.35 DROP COLUMN; the repo
        # runs 3.45). Makes the rename self-clearing so the 75.1 scanner's
        # DB-only-column warning does not fire on every startup forever.
        connection.execute(text("ALTER TABLE room DROP COLUMN area_id"))
    logger.info("room-migration: folded area_id → zone/room_type and dropped area_id")
