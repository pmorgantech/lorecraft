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
