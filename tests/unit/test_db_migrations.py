"""Tests for the Sprint 75 SQLite additive-column scanner + PK-rename migrations.

All tests run against real temp-file SQLite engines (not ``:memory:``) so
``ALTER``/table-rebuild round-trip through genuine reflection, exercising the
same code path a legacy ``var/app.sqlite`` upgrade hits on startup.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Engine, create_engine, inspect, text
from sqlmodel import Session, SQLModel

from lorecraft.db import (
    _ensure_additive_columns,
    _ensure_scheduledjob_status_due_index,
    _migrate_regionpricing_area_id,
    _migrate_room_area_id,
    create_game_tables,
)
from lorecraft.engine.models.player import SaveSlot
from lorecraft.engine.models.scheduler import ScheduledJob
from lorecraft.engine.models.world import NPC, Item, Room


def _file_engine(tmp_path: Path, name: str = "game.db") -> Engine:
    """A real temp-file SQLite engine (reflection needs a persisted schema)."""
    return create_engine(f"sqlite:///{tmp_path / name}")


def _columns(engine: Engine, table: str) -> set[str]:
    return {col["name"] for col in inspect(engine).get_columns(table)}


# --- 1. Additive-column upgrade with field-derived defaults -------------------


def _make_item() -> Item:
    return Item(id="itm", name="Item", description="d")


def _make_room() -> Room:
    return Room(id="rm", name="Room", description="d", map_x=0, map_y=0)


def _make_saveslot() -> SaveSlot:
    return SaveSlot(player_id="p1", slot_name="s", saved_at=0.0, room_id="rm")


def _make_npc() -> NPC:
    return NPC(
        id="npc",
        name="N",
        description="d",
        current_room_id="rm",
        home_room_id="rm",
        dialogue_tree_id="dt",
    )


# (model, factory, table, column, expected readback of a pre-existing row).
# Each expected value is the *field-derived* default — a naive type-zero table
# would corrupt the two string cases to '' and the JSON cases to NULL/''.
_ADDITIVE_CASES: list[
    tuple[type[SQLModel], Callable[[], SQLModel], str, str, object]
] = [
    (Item, _make_item, "item", "quality", "common"),
    (Room, _make_room, "room", "terrain", "normal"),
    (SaveSlot, _make_saveslot, "saveslot", "visited_rooms", "[]"),
    (Item, _make_item, "item", "mechanism_side_effects", "{}"),
    (NPC, _make_npc, "npc", "following_player_id", None),
]


@pytest.mark.parametrize(
    "model, factory, table, column, expected",
    _ADDITIVE_CASES,
    ids=[f"{c[2]}.{c[3]}" for c in _ADDITIVE_CASES],
)
def test_additive_column_upgrade_uses_field_derived_default(
    tmp_path: Path,
    model: type[SQLModel],
    factory: Callable[[], SQLModel],
    table: str,
    column: str,
    expected: object,
) -> None:
    engine = _file_engine(tmp_path)
    model.__table__.create(engine)  # type: ignore[attr-defined]
    with Session(engine) as session:
        session.add(factory())
        session.commit()

    # Simulate a legacy DB predating the column: drop it (and its data) from the
    # otherwise-complete table, leaving a row with no value for it at all.
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
    assert column not in _columns(engine, table)

    _ensure_additive_columns(engine)

    assert column in _columns(engine, table)
    with engine.connect() as conn:
        value = conn.execute(text(f"SELECT {column} FROM {table}")).scalar()
    # The re-added column's value can only come from the migration's DEFAULT,
    # so this asserts the DEFAULT is the field-derived value, not a type-zero.
    assert value == expected


def test_additive_scanner_skips_nothing_when_schema_is_current(tmp_path: Path) -> None:
    # A freshly-created full schema needs no ALTERs; the scanner must be a no-op.
    engine = _file_engine(tmp_path)
    Item.__table__.create(engine)  # type: ignore[attr-defined]
    before = _columns(engine, "item")
    _ensure_additive_columns(engine)
    assert _columns(engine, "item") == before


# --- 2. Room area_id → zone/room_type fold round-trip ------------------------

# The full §71.2 fold table: (legacy area_id, expected zone, expected room_type).
# room_type is derivable only for the three Ashmoore kinds; NULL elsewhere.
_ROOM_FOLD: list[tuple[str, str, str | None]] = [
    ("town", "ashmoore", "town"),
    ("wilderness", "ashmoore", "wilderness"),
    ("cave", "ashmoore", "cave"),
    ("cogsworth", "cogsworth", None),
    ("whisperwood", "whisperwood", None),
    ("port_veridian", "port_veridian", None),
    ("old_trade_road", "cogsworth", None),
    ("forest_road", "whisperwood", None),
    ("river_bend", "port_veridian", None),
]


@pytest.fixture(scope="module")
def migrated_room_engine(tmp_path_factory: pytest.TempPathFactory) -> Engine:
    """A room table seeded with every legacy area_id value, then migrated once."""
    path = tmp_path_factory.mktemp("room-migration") / "game.db"
    engine = create_engine(f"sqlite:///{path}")
    Room.__table__.create(engine)  # type: ignore[attr-defined]
    # Post-75.1-scan shape: zone/room_type already added (empty), area_id lingering.
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE room ADD COLUMN area_id VARCHAR"))
    with Session(engine) as session:
        for area_id, _zone, _rt in _ROOM_FOLD:
            session.add(
                Room(id=f"room-{area_id}", name="N", description="D", map_x=0, map_y=0)
            )
        session.commit()
    with engine.begin() as conn:
        for area_id, _zone, _rt in _ROOM_FOLD:
            conn.execute(
                text("UPDATE room SET area_id = :a WHERE id = :id"),
                {"a": area_id, "id": f"room-{area_id}"},
            )
    _migrate_room_area_id(engine)
    return engine


@pytest.mark.parametrize(
    "area_id, expected_zone, expected_room_type",
    _ROOM_FOLD,
    ids=[c[0] for c in _ROOM_FOLD],
)
def test_room_area_id_folds_to_zone_and_room_type(
    migrated_room_engine: Engine,
    area_id: str,
    expected_zone: str,
    expected_room_type: str | None,
) -> None:
    with migrated_room_engine.connect() as conn:
        row = conn.execute(
            text("SELECT zone, room_type FROM room WHERE id = :id"),
            {"id": f"room-{area_id}"},
        ).one()
    assert row.zone == expected_zone
    assert row.room_type == expected_room_type


def test_room_migration_drops_legacy_area_id(migrated_room_engine: Engine) -> None:
    assert "area_id" not in _columns(migrated_room_engine, "room")


def test_room_migration_is_idempotent(tmp_path: Path) -> None:
    engine = _file_engine(tmp_path)
    Room.__table__.create(engine)  # type: ignore[attr-defined]
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE room ADD COLUMN area_id VARCHAR"))
    with Session(engine) as session:
        session.add(Room(id="r1", name="N", description="D", map_x=0, map_y=0))
        session.commit()
    with engine.begin() as conn:
        conn.execute(text("UPDATE room SET area_id = 'town' WHERE id = 'r1'"))

    _migrate_room_area_id(engine)
    _migrate_room_area_id(engine)  # second run must be a clean no-op

    with engine.connect() as conn:
        row = conn.execute(text("SELECT zone, room_type FROM room")).one()
    assert row.zone == "ashmoore"
    assert row.room_type == "town"


# --- 3. RegionPricing area_id(PK) → zone(PK) rebuild round-trip --------------


def _seed_legacy_regionpricing(
    engine: Engine, rows: list[tuple[str, float, str]]
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE regionpricing "
                "(area_id VARCHAR PRIMARY KEY, region_mult FLOAT, bias JSON)"
            )
        )
        for area_id, region_mult, bias in rows:
            conn.execute(
                text("INSERT INTO regionpricing VALUES (:a, :m, :b)"),
                {"a": area_id, "m": region_mult, "b": bias},
            )


def test_regionpricing_rebuild_folds_six_rows_into_four_zones(tmp_path: Path) -> None:
    engine = _file_engine(tmp_path)
    _seed_legacy_regionpricing(
        engine,
        [
            ("town", 1.0, "{}"),
            ("wilderness", 1.15, "{}"),
            ("cave", 1.25, "{}"),
            ("cogsworth", 1.1, '{"copper_coin": 1.2}'),
            ("whisperwood", 1.05, "{}"),
            ("port_veridian", 0.95, "{}"),
        ],
    )

    _migrate_regionpricing_area_id(engine)

    with engine.connect() as conn:
        result = {
            row.zone: row.region_mult
            for row in conn.execute(
                text("SELECT zone, region_mult FROM regionpricing")
            ).all()
        }
    assert result == {
        "ashmoore": 1.0,
        "cogsworth": 1.1,
        "whisperwood": 1.05,
        "port_veridian": 0.95,
    }
    # zone must genuinely be the primary key now, not merely a present column.
    pk = inspect(engine).get_pk_constraint("regionpricing")["constrained_columns"]
    assert pk == ["zone"]
    assert "area_id" not in _columns(engine, "regionpricing")
    # per-zone bias must survive the rebuild.
    with engine.connect() as conn:
        bias = conn.execute(
            text("SELECT bias FROM regionpricing WHERE zone = 'cogsworth'")
        ).scalar()
    assert bias == '{"copper_coin": 1.2}'


def test_regionpricing_forces_ashmoore_mult_to_one_regardless_of_source(
    tmp_path: Path,
) -> None:
    # OPEN ITEM B: seed all three Ashmoore source rows with multipliers that are
    # NOT 1.0, so a mere GROUP-BY row-pick could never yield 1.0. The fold must
    # still force the collapsed ashmoore row to exactly 1.0.
    engine = _file_engine(tmp_path)
    _seed_legacy_regionpricing(
        engine,
        [
            ("town", 0.8, "{}"),
            ("wilderness", 1.15, "{}"),
            ("cave", 1.25, "{}"),
        ],
    )

    _migrate_regionpricing_area_id(engine)

    with engine.connect() as conn:
        mult = conn.execute(
            text("SELECT region_mult FROM regionpricing WHERE zone = 'ashmoore'")
        ).scalar()
    assert mult == 1.0


def test_regionpricing_rebuild_is_idempotent(tmp_path: Path) -> None:
    engine = _file_engine(tmp_path)
    _seed_legacy_regionpricing(engine, [("cogsworth", 1.1, "{}")])

    _migrate_regionpricing_area_id(engine)
    _migrate_regionpricing_area_id(engine)  # second run: table already zone-keyed

    with engine.connect() as conn:
        result = conn.execute(text("SELECT zone, region_mult FROM regionpricing")).all()
    assert [(r.zone, r.region_mult) for r in result] == [("cogsworth", 1.1)]


def test_regionpricing_rebuild_recovers_from_stray_new_table(tmp_path: Path) -> None:
    # A crash between the CREATE and the final rename can leave `regionpricing_new`
    # behind after a rollback restores the original table. The next boot re-runs
    # the migration; a bare CREATE would fail with "table already exists" and brick
    # every subsequent start. Drop-first must let the rebuild complete regardless of
    # the leftover's (here deliberately wrong) schema.
    engine = _file_engine(tmp_path)
    _seed_legacy_regionpricing(engine, [("cogsworth", 1.1, '{"copper_coin": 1.2}')])
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE regionpricing_new (bogus VARCHAR)"))

    _migrate_regionpricing_area_id(engine)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT zone, region_mult FROM regionpricing")).all()
    assert [(r.zone, r.region_mult) for r in result] == [("cogsworth", 1.1)]
    pk = inspect(engine).get_pk_constraint("regionpricing")["constrained_columns"]
    assert pk == ["zone"]
    assert "regionpricing_new" not in inspect(engine).get_table_names()


def test_regionpricing_fold_collision_is_deterministic_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Not reachable with current world content (connector zones carry no pricing
    # rows), but if two non-Ashmoore source rows ever fold onto the same zone the
    # result must be deterministic — lowest area_id wins via the ORDER BY — and the
    # violated 1:1 invariant must surface as a WARNING, not silently last-wins.
    engine = _file_engine(tmp_path)
    _seed_legacy_regionpricing(
        engine,
        [
            ("cogsworth", 1.1, "{}"),  # folds to zone cogsworth (kept: lower area_id)
            ("old_trade_road", 2.2, "{}"),  # also folds to cogsworth (ignored)
        ],
    )

    with caplog.at_level(logging.WARNING):
        _migrate_regionpricing_area_id(engine)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT zone, region_mult FROM regionpricing")).all()
    assert [(r.zone, r.region_mult) for r in result] == [("cogsworth", 1.1)]
    assert any("fold onto zone=cogsworth" in rec.message for rec in caplog.records)


# --- 4. Warn-but-don't-drop for a DB-only column -----------------------------


def test_scanner_warns_but_never_drops_db_only_column(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    engine = _file_engine(tmp_path)
    Item.__table__.create(engine)  # type: ignore[attr-defined]
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE item ADD COLUMN legacy_extra TEXT"))

    with caplog.at_level(logging.WARNING, logger="lorecraft.db"):
        _ensure_additive_columns(engine)

    # Strictly-additive contract: the unknown column survives untouched...
    assert "legacy_extra" in _columns(engine, "item")
    # ...but the scanner flags it.
    assert any("legacy_extra" in record.message for record in caplog.records)


# --- 5. Full-path idempotency ------------------------------------------------


def _schema_snapshot(engine: Engine) -> dict[str, list[str]]:
    inspector = inspect(engine)
    return {
        table: sorted(col["name"] for col in inspector.get_columns(table))
        for table in sorted(inspector.get_table_names())
    }


def test_full_migration_path_is_idempotent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    engine = _file_engine(tmp_path)
    # Legacy-ish DB: room with a lingering area_id + regionpricing on the old PK.
    Room.__table__.create(engine)  # type: ignore[attr-defined]
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE room ADD COLUMN area_id VARCHAR"))
    with Session(engine) as session:
        session.add(Room(id="r1", name="N", description="D", map_x=0, map_y=0))
        session.commit()
    with engine.begin() as conn:
        conn.execute(text("UPDATE room SET area_id = 'town' WHERE id = 'r1'"))
    _seed_legacy_regionpricing(engine, [("cogsworth", 1.1, "{}")])

    # First full path: creates the rest of the schema, scans, and migrates.
    create_game_tables(engine)
    schema_after_first = _schema_snapshot(engine)

    # Second full path must issue no ALTER/fold/rebuild. caplog accumulates over
    # the whole test, so clear the first run's records first (they are only
    # captured at all when the ambient log level is INFO — e.g. under the full
    # suite — which is exactly when a stale record would produce a false failure).
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="lorecraft.db"):
        create_game_tables(engine)

    action_markers = ("added column", "folded area_id", "rebuilt with zone")
    action_logs = [
        record
        for record in caplog.records
        if any(marker in record.message for marker in action_markers)
    ]
    assert action_logs == []
    assert _schema_snapshot(engine) == schema_after_first


# --- 6. Non-SQLite dialect guard ---------------------------------------------


def test_migrations_are_noop_on_non_sqlite_dialect() -> None:
    engine: Any = MagicMock()
    engine.dialect.name = "postgresql"

    assert _ensure_additive_columns(engine) is None
    assert _migrate_room_area_id(engine) is None
    assert _migrate_regionpricing_area_id(engine) is None
    assert _ensure_scheduledjob_status_due_index(engine) is None

    # Early-return before touching the DB at all.
    engine.begin.assert_not_called()
    engine.connect.assert_not_called()


# --- 7. PlayerStats.skills -> discipline_ranks additive rename (Sprint 78.3) --


def test_discipline_ranks_added_and_legacy_skills_left_as_dead_column(
    tmp_path: Path,
) -> None:
    """A pre-78 DB (flat `skills` JSON column, no `discipline_ranks`) upgrades by
    ADDing `discipline_ranks` and leaving the legacy `skills` column untouched.

    The additive scanner is strictly additive — it cannot DROP — so the old
    column lingers as a warned, ignored dead column (Sprint 75 precedent). The
    new column is what the model reads/writes going forward.
    """
    from lorecraft.engine.models.player import PlayerStats

    engine = _file_engine(tmp_path)
    PlayerStats.__table__.create(engine)  # type: ignore[attr-defined]
    # Simulate the legacy shape: drop the new column, re-add the old `skills` one,
    # then seed a row via raw SQL (the ORM would insert the new column we dropped).
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE playerstats DROP COLUMN discipline_ranks"))
        conn.execute(text("ALTER TABLE playerstats ADD COLUMN skills JSON"))
        conn.execute(
            text(
                "INSERT INTO playerstats "
                "(player_id, strength, agility, vitality, intellect, presence, "
                "fortitude, max_hp, level, xp, xp_to_next, skill_points, skills, "
                "traits, unlocked_nodes) "
                "VALUES ('p1', 10, 10, 10, 10, 10, 10, 100, 1, 0, 100, 0, "
                "'{\"perception\": 12}', '[]', '[]')"
            )
        )
    assert "discipline_ranks" not in _columns(engine, "playerstats")

    _ensure_additive_columns(engine)

    cols = _columns(engine, "playerstats")
    assert "discipline_ranks" in cols  # added by the scanner
    assert "skills" in cols  # legacy column left in place, not dropped
    # The new column reads back its field-derived default ({}), independent of
    # the stranded legacy data — no silent data migration is claimed.
    with engine.connect() as conn:
        value = conn.execute(
            text("SELECT discipline_ranks FROM playerstats WHERE player_id = 'p1'")
        ).scalar()
    assert value == "{}"


# --- 8. ScheduledJob composite (status, due_at_epoch) index -------------------


def _index_names(engine: Engine, table: str) -> set[str]:
    return {idx["name"] for idx in inspect(engine).get_indexes(table)}


def test_scheduledjob_composite_index_added_to_legacy_table(tmp_path: Path) -> None:
    """A table created before the composite index existed (single-column
    ``due_at_epoch``/``job_type`` indexes only) gets the composite index added.
    """
    engine = _file_engine(tmp_path)
    # Simulate the pre-fix schema: no composite index, single-column ones only.
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE scheduledjob ("
                "id VARCHAR NOT NULL PRIMARY KEY, "
                "job_type VARCHAR NOT NULL, "
                "due_at_epoch FLOAT NOT NULL, "
                "status VARCHAR NOT NULL, "
                "payload JSON NOT NULL, "
                "created_at FLOAT NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX ix_scheduledjob_due_at_epoch ON scheduledjob (due_at_epoch)"
            )
        )
    assert "ix_scheduledjob_status_due_at_epoch" not in _index_names(
        engine, "scheduledjob"
    )

    _ensure_scheduledjob_status_due_index(engine)

    assert "ix_scheduledjob_status_due_at_epoch" in _index_names(engine, "scheduledjob")


def test_scheduledjob_composite_index_is_idempotent(tmp_path: Path) -> None:
    engine = _file_engine(tmp_path)
    ScheduledJob.__table__.create(engine)  # type: ignore[attr-defined]

    _ensure_scheduledjob_status_due_index(engine)
    _ensure_scheduledjob_status_due_index(engine)  # must not raise (IF NOT EXISTS)

    assert "ix_scheduledjob_status_due_at_epoch" in _index_names(engine, "scheduledjob")


def test_scheduledjob_composite_index_missing_table_is_noop(tmp_path: Path) -> None:
    """No `scheduledjob` table at all (brand-new DB pre-`create_all`) is a no-op,
    not an error — `_create_model_tables` will create the table (with the index
    already declared in the model) before this migration ever runs in practice.
    """
    engine = _file_engine(tmp_path)
    _ensure_scheduledjob_status_due_index(engine)  # must not raise


def test_scheduledjob_query_plan_uses_composite_index(tmp_path: Path) -> None:
    """The actual `SchedulerRepo.due()` predicate seeks via the composite index
    instead of scanning the single-column `due_at_epoch` index — proving the fix
    addresses the diagnosed query plan, not just adding an unused index.
    """
    engine = _file_engine(tmp_path)
    ScheduledJob.__table__.create(engine)  # type: ignore[attr-defined]

    with engine.connect() as conn:
        plan = conn.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT * FROM scheduledjob "
                "WHERE status = 'pending' AND due_at_epoch <= 123.0"
            )
        ).all()
    plan_text = " ".join(str(row) for row in plan)
    assert "ix_scheduledjob_status_due_at_epoch" in plan_text


def test_full_migration_path_creates_scheduledjob_composite_index(
    tmp_path: Path,
) -> None:
    """`create_game_tables` on a brand-new DB ends up with the composite index
    via the model's `__table_args__` (not the migration function, which only
    matters for pre-existing legacy tables) — proving the two paths agree.
    """
    engine = _file_engine(tmp_path)
    create_game_tables(engine)
    assert "ix_scheduledjob_status_due_at_epoch" in _index_names(engine, "scheduledjob")
