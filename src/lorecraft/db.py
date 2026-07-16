"""Database engine and table initialization helpers.

The reflection-based additive-column auto-migration scanner below lives here
rather than under ``engine/`` deliberately: ``db.py`` is a **composition-layer**
module (it already imports ``lorecraft.features.*`` across ``GAME_TABLE_MODELS``),
not Tier 1 engine infra, so ``test_tier_boundaries.py`` does not gate it. The
scanner mechanism is *Tier-1 in character* — opinion-free reflection that knows
only *how* to diff-and-``ALTER``, never *what* a column means for any feature.

The one caveat is the two fold-maps (``_ROOM_AREA_ID_TO_ZONE`` /
``_REGIONPRICING_AREA_ID_TO_ZONE``) used by the Sprint 71.2 ``area_id`` data
migrations: they embed Sprint 71.2 world-content literals directly here. That is
accepted as a **bounded, self-clearing, one-shot historical migration constant**
(it transforms *past* data to a *known* target state — it is not runtime
branching on room IDs) and is a deliberate, documented exception, not clean
Tier 1. Once ``area_id`` is dropped (room) and the ``regionpricing`` table
rebuilt, both fold-maps become dead code.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
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
from lorecraft.features.combat.models import (
    CombatAction,
    CombatEncounter,
    CombatParticipant,
    CombatRelationship,
    CombatResolutionRecord,
    CombatRulesetConfig,
    CombatWound,
)
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
    CombatEncounter,
    CombatParticipant,
    CombatRelationship,
    CombatAction,
    CombatResolutionRecord,
    CombatWound,
    CombatRulesetConfig,
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

# RegionPricing shares the same geographic fold as rooms.
_REGIONPRICING_AREA_ID_TO_ZONE: Mapping[str, str] = _ROOM_AREA_ID_TO_ZONE


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


def configure_query_logging(
    engine: Engine, settings: Settings, *, engine_role: str
) -> Engine:
    """Attach JSONL SQL timing hooks to an engine.

    The listener logs one non-DB line per executed cursor statement, with query
    parameters deliberately reduced to counts only. This is composition-layer
    observability: it measures DB access patterns without changing game policy
    or adding audit-table write volume.
    """
    if not settings.db_query_log_enabled:
        return engine
    if getattr(engine, "_lorecraft_query_logging_configured", False):
        return engine

    log_path = Path(settings.db_query_log_path)
    slow_ms = settings.db_query_slow_ms

    @event.listens_for(engine, "before_cursor_execute")
    def _start_query_timer(
        conn: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        stack = conn.info.setdefault("lorecraft_query_start_stack", [])
        stack.append((time.perf_counter(), statement))

    @event.listens_for(engine, "after_cursor_execute")
    def _log_query_timing(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        _context: Any,
        executemany: bool,
    ) -> None:
        stack = conn.info.setdefault("lorecraft_query_start_stack", [])
        started_at, original_statement = (
            stack.pop() if stack else (time.perf_counter(), statement)
        )
        duration_ms = (time.perf_counter() - started_at) * 1000.0
        normalized = _normalize_sql_for_log(original_statement)
        payload = {
            "ts": datetime.now(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "engine_role": engine_role,
            "dialect": engine.dialect.name,
            "duration_ms": round(duration_ms, 3),
            "slow": duration_ms >= slow_ms,
            "slow_threshold_ms": slow_ms,
            "statement_type": _statement_type(normalized),
            "statement_hash": _statement_hash(normalized),
            "statement": normalized,
            "rowcount": cursor.rowcount if cursor.rowcount >= 0 else None,
            "executemany": executemany,
            "parameter_count": _parameter_count(parameters, executemany),
        }
        _append_query_log(log_path, payload)

    setattr(engine, "_lorecraft_query_logging_configured", True)
    return engine


def _normalize_sql_for_log(statement: str) -> str:
    return " ".join(statement.split())


def _statement_type(statement: str) -> str:
    first, _separator, _rest = statement.partition(" ")
    return first.upper()


def _statement_hash(statement: str) -> str:
    return hashlib.sha256(statement.encode("utf-8")).hexdigest()[:16]


def _parameter_count(parameters: Any, executemany: bool) -> int:
    if parameters is None:
        return 0
    if (
        executemany
        and isinstance(parameters, Sequence)
        and not isinstance(parameters, (str, bytes, bytearray))
    ):
        return sum(_parameter_count(item, False) for item in parameters)
    if isinstance(parameters, Mapping):
        return len(parameters)
    if isinstance(parameters, Sequence) and not isinstance(
        parameters, (str, bytes, bytearray)
    ):
        return len(parameters)
    return 1


def _append_query_log(log_path: Path, payload: Mapping[str, object]) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
    except OSError:
        logger.warning("query-log: failed to append %s", log_path, exc_info=True)


def create_game_engine(
    settings: Settings | None = None, *, echo: bool = False
) -> Engine:
    settings = settings or load_settings()
    url = database_url(settings.database_path)
    engine = create_engine(url, echo=echo, **_pool_kwargs(url, settings))
    configure_sqlite_engine(engine, settings)
    return configure_query_logging(engine, settings, engine_role="game")


def create_audit_engine(
    settings: Settings | None = None, *, echo: bool = False
) -> Engine:
    settings = settings or load_settings()
    url = database_url(settings.audit_database_path)
    engine = create_engine(url, echo=echo, **_pool_kwargs(url, settings))
    configure_sqlite_engine(engine, settings)
    return configure_query_logging(engine, settings, engine_role="audit")


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
    # Deliberate Sprint 78.3 cleanup: the generic scanner adds
    # playerstats.discipline_ranks, but a dedicated migration must drop the
    # orphaned pre-78 playerstats.skills column so startup warnings self-clear.
    _migrate_playerstats_skills(engine)
    # Deliberate Sprint 71.2 room data migration (Sprint 75.3). Runs *after* the
    # additive pass, which will already have added room.zone / room.room_type as
    # empty nullable columns to fold the legacy area_id into.
    _migrate_room_area_id(engine)
    # RegionPricing area_id(PK) → zone(PK) table-rebuild (Sprint 75.4). A PK
    # rename can't go through ALTER, so it needs a full rebuild of its own.
    _migrate_regionpricing_area_id(engine)
    # Composite (status, due_at_epoch) index for SchedulerRepo.due() — the
    # additive-column scanner above never adds indexes, only columns.
    _ensure_scheduledjob_status_due_index(engine)


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


def _migrate_playerstats_skills(engine: Engine) -> None:
    """Drop the legacy ``playerstats.skills`` column after Sprint 78.3.

    Sprint 78 renamed the flat skills storage to ``discipline_ranks`` with a
    different keyspace, so there is no safe data fold to perform here. The
    additive scanner has already added ``discipline_ranks`` with its default
    ``{}``; this one-shot migration only removes the orphaned pre-78 column so
    the scanner's DB-only-column warning does not fire forever.
    """
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "playerstats" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("playerstats")}
    if "skills" not in columns or "discipline_ranks" not in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE playerstats DROP COLUMN skills"))
    logger.info("playerstats-migration: dropped legacy skills column")


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


def _migrate_regionpricing_area_id(engine: Engine) -> None:
    """Rebuild ``regionpricing`` from ``area_id`` PK to ``zone`` PK (Sprint 75.4).

    ``zone`` is the PRIMARY KEY, so neither ``ADD COLUMN … PRIMARY KEY`` nor
    ``DROP COLUMN area_id`` is possible in SQLite — this needs the classic
    table-rebuild. Guarded on the live table still carrying an ``area_id`` column
    (a no-op on a fresh / already-migrated DB).

    The fold collapses Ashmoore's three source rows onto one ``zone='ashmoore'``
    PK, so grouping on the *folded* value is mandatory. Per OPEN ITEM B, the
    collapsed ``ashmoore`` row's ``region_mult`` is forced to ``1.0`` explicitly
    (matching §71.2's decision — Ashmoore's only shop is a ``town``/1.0 room, and
    the ``wilderness``/``cave`` multipliers were inert) rather than trusting an
    arbitrary aggregate row-pick. Rebuild-with-fold (OPEN ITEM C) keeps prices
    correct on an in-place legacy upgrade with no reseed.
    """
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "regionpricing" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("regionpricing")}
    if "area_id" not in columns:
        return  # already zone-keyed (fresh or already-migrated)

    with engine.begin() as connection:
        # ORDER BY area_id makes the fold deterministic even if the 1:1
        # non-Ashmoore zone→row invariant is ever violated (see the non-Ashmoore
        # branch below): the lowest-area_id row is the one kept.
        rows = connection.execute(
            text(
                "SELECT area_id, region_mult, bias FROM regionpricing ORDER BY area_id"
            )
        ).all()

        # zone -> (region_mult, bias_json). Fold in Python so the Ashmoore
        # region_mult can be forced to 1.0 deterministically (OPEN ITEM B) and
        # the collapsed bias is chosen deterministically (prefer the `town`
        # source row — Ashmoore's only shop — else first-seen).
        folded: dict[str, tuple[float, str]] = {}
        for area_id, region_mult, bias in rows:
            zone = _REGIONPRICING_AREA_ID_TO_ZONE.get(area_id, area_id)
            bias_json = bias if bias is not None else "{}"
            if zone == "ashmoore":
                if zone not in folded or area_id == "town":
                    folded[zone] = (1.0, bias_json)
            else:
                # Non-Ashmoore zones are 1:1 with a single pricing source row in
                # all current world content (the connector zones fold onto a
                # canonical zone that carries the only pricing row). Keep the
                # first-seen (lowest area_id, per ORDER BY) row deterministically,
                # but surface any real collision with differing values rather than
                # silently last-wins over an unordered SELECT.
                candidate = (float(region_mult), bias_json)
                existing = folded.get(zone)
                if existing is not None and existing != candidate:
                    logger.warning(
                        "regionpricing-migration: multiple source rows fold onto "
                        "zone=%s with differing pricing (area_id=%s); keeping the "
                        "first-seen %r, ignoring %r — the 1:1 zone→row invariant "
                        "was violated",
                        zone,
                        area_id,
                        existing,
                        candidate,
                    )
                    continue
                folded[zone] = candidate

        # Drop-first (not CREATE … IF NOT EXISTS): SQLite autocommits DDL outside
        # a transaction, so a crash between this CREATE and the final rename can
        # leave a stray `regionpricing_new` behind after rollback restores the
        # original table. On the next boot the guard re-triggers and a bare CREATE
        # would fail with "table already exists", bricking every subsequent start.
        # Dropping first is safer than IF NOT EXISTS, which could reuse a stale
        # leftover of the wrong schema.
        connection.execute(text("DROP TABLE IF EXISTS regionpricing_new"))
        connection.execute(
            text(
                "CREATE TABLE regionpricing_new ("
                "zone VARCHAR NOT NULL PRIMARY KEY, "
                "region_mult FLOAT NOT NULL DEFAULT 1.0, "
                "bias JSON NOT NULL DEFAULT '{}')"
            )
        )
        for zone, (region_mult, bias_json) in folded.items():
            connection.execute(
                text(
                    "INSERT INTO regionpricing_new (zone, region_mult, bias) "
                    "VALUES (:zone, :region_mult, :bias)"
                ),
                {"zone": zone, "region_mult": region_mult, "bias": bias_json},
            )
        connection.execute(text("DROP TABLE regionpricing"))
        connection.execute(
            text("ALTER TABLE regionpricing_new RENAME TO regionpricing")
        )
    logger.info(
        "regionpricing-migration: rebuilt with zone PK (%d zone rows)", len(folded)
    )


def _ensure_scheduledjob_status_due_index(engine: Engine) -> None:
    """Add the composite ``(status, due_at_epoch)`` index to a legacy DB.

    ``_ensure_additive_columns`` only reconciles columns, never indexes, so a DB
    created before this composite index was added to the model never gets it —
    ``table.create(engine, checkfirst=True)`` is a no-op once the table exists.

    Load-bearing for `SchedulerRepo.due()`'s per-tick query (diagnosed live: a
    dev DB with 141k dispatched rows and 6 pending ones took ~25ms on this query
    alone without the composite index, because SQLite's only option was a scan
    of the single-column ``due_at_epoch`` index — which matches nearly every
    historical row, since ``due_at_epoch`` never exceeds the ever-advancing
    current epoch — filtering for ``status`` one row at a time). ``CREATE INDEX
    IF NOT EXISTS`` makes this idempotent without needing a live-index inspector
    round-trip.
    """
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "scheduledjob" not in inspector.get_table_names():
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_scheduledjob_status_due_at_epoch "
                "ON scheduledjob (status, due_at_epoch)"
            )
        )
    logger.info(
        "scheduledjob-migration: ensured composite (status, due_at_epoch) index"
    )
