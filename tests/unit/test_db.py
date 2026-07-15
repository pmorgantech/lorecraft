import json
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlmodel import create_engine

from lorecraft.config import Settings, load_settings
from lorecraft.db import (
    AUDIT_TABLE_MODELS,
    GAME_TABLE_MODELS,
    _pool_kwargs,
    configure_sqlite_engine,
    create_audit_tables,
    create_game_engine,
    create_game_tables,
    configure_query_logging,
    create_tables,
)


def test_create_tables_separates_game_and_audit_tables() -> None:
    game_engine = create_engine("sqlite://")
    audit_engine = create_engine("sqlite://")

    create_tables(game_engine=game_engine, audit_engine=audit_engine)

    game_tables = set(inspect(game_engine).get_table_names())
    audit_tables = set(inspect(audit_engine).get_table_names())

    assert game_tables == {model.__tablename__ for model in GAME_TABLE_MODELS}
    assert audit_tables == {model.__tablename__ for model in AUDIT_TABLE_MODELS}
    assert "auditevent" not in game_tables


def test_create_audit_tables_initializes_only_audit_schema() -> None:
    audit_engine = create_engine("sqlite://")

    create_audit_tables(audit_engine)

    audit_tables = set(inspect(audit_engine).get_table_names())
    assert audit_tables == {model.__tablename__ for model in AUDIT_TABLE_MODELS}
    assert not ({model.__tablename__ for model in GAME_TABLE_MODELS} & audit_tables)


def test_compat_shim_adds_skill_points_to_legacy_playerstats() -> None:
    # Simulate a var/app.sqlite created before PlayerStats.skill_points (Sprint 73):
    # a playerstats table missing the column. create_game_tables' checkfirst leaves
    # the pre-existing table alone, so the compat shim is the only path that adds it.
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE playerstats ("
                "player_id TEXT PRIMARY KEY, "
                "strength INTEGER NOT NULL DEFAULT 10, "
                "level INTEGER NOT NULL DEFAULT 1, "
                "xp INTEGER NOT NULL DEFAULT 0)"
            )
        )
        conn.execute(
            text("INSERT INTO playerstats (player_id) VALUES ('legacy-player')")
        )

    assert "skill_points" not in {
        c["name"] for c in inspect(engine).get_columns("playerstats")
    }

    create_game_tables(engine)

    columns = {c["name"] for c in inspect(engine).get_columns("playerstats")}
    assert "skill_points" in columns
    with engine.connect() as conn:
        value = conn.execute(
            text(
                "SELECT skill_points FROM playerstats WHERE player_id = 'legacy-player'"
            )
        ).scalar()
    assert value == 0


def test_pool_kwargs_empty_for_sqlite() -> None:
    # SQLite is single-writer; QueuePool sizing knobs don't apply.
    settings = Settings(db_pool_size=20, db_pool_recycle=600)
    assert _pool_kwargs("sqlite:///game.db", settings) == {}
    assert _pool_kwargs("sqlite://", settings) == {}


def test_pool_kwargs_configured_for_networked_backend() -> None:
    settings = Settings(db_pool_size=20, db_pool_recycle=600)
    assert _pool_kwargs("postgresql+psycopg://user@host/db", settings) == {
        "pool_size": 20,
        "pool_recycle": 600,
    }


def test_load_settings_reads_pool_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LORECRAFT_DB_POOL_SIZE", "15")
    monkeypatch.setenv("LORECRAFT_DB_POOL_RECYCLE", "900")
    settings = load_settings()
    assert settings.db_pool_size == 15
    assert settings.db_pool_recycle == 900


def test_create_game_engine_enables_wal_on_file_db(tmp_path: Path) -> None:
    db_path = tmp_path / "wal.db"
    engine = create_game_engine(Settings(database_path=str(db_path)))
    with engine.connect() as conn:
        journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()
        synchronous = conn.execute(text("PRAGMA synchronous")).scalar()
    assert journal_mode == "wal"
    assert synchronous == 1  # NORMAL


def test_configure_sqlite_engine_respects_full_synchronous(tmp_path: Path) -> None:
    db_path = tmp_path / "full.db"
    engine = create_game_engine(
        Settings(database_path=str(db_path), db_sqlite_synchronous="FULL")
    )
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA synchronous")).scalar() == 2  # FULL


def test_configure_sqlite_engine_rejects_invalid_synchronous(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'x.db'}")
    with pytest.raises(ValueError, match="db_sqlite_synchronous"):
        configure_sqlite_engine(engine, Settings(db_sqlite_synchronous="BOGUS"))


def test_load_settings_reads_sqlite_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LORECRAFT_DB_SQLITE_WAL", "false")
    monkeypatch.setenv("LORECRAFT_DB_SQLITE_SYNCHRONOUS", "FULL")
    settings = load_settings()
    assert settings.db_sqlite_wal is False
    assert settings.db_sqlite_synchronous == "FULL"


def test_load_settings_reads_content_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LORECRAFT_COMBAT_ACTIONS_YAML_PATH", "/tmp/actions.yaml")
    settings = load_settings()
    assert settings.combat_actions_yaml_path == "/tmp/actions.yaml"


def test_query_logging_writes_jsonl_without_parameter_values(tmp_path: Path) -> None:
    log_path = tmp_path / "queries.log"
    engine = create_game_engine(
        Settings(
            database_path=":memory:",
            db_query_log_path=str(log_path),
            db_query_slow_ms=0.0,
        )
    )

    with engine.connect() as connection:
        connection.execute(text("SELECT :secret AS value"), {"secret": "hidden"})

    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    select_record = next(
        record for record in records if record["statement_type"] == "SELECT"
    )
    assert select_record["engine_role"] == "game"
    assert select_record["statement"] == "SELECT ? AS value"
    assert select_record["parameter_count"] == 1
    assert "hidden" not in log_path.read_text()
    assert select_record["slow"] is True


def test_configure_query_logging_can_be_disabled(tmp_path: Path) -> None:
    log_path = tmp_path / "queries.log"
    engine = create_engine("sqlite://")
    configure_query_logging(
        engine,
        Settings(db_query_log_enabled=False, db_query_log_path=str(log_path)),
        engine_role="game",
    )

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    assert not log_path.exists()
