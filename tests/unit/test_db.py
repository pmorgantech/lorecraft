from sqlalchemy import inspect
from sqlmodel import create_engine

from lorecraft.db import AUDIT_TABLE_MODELS, GAME_TABLE_MODELS, create_tables


def test_create_tables_separates_game_and_audit_tables() -> None:
    game_engine = create_engine("sqlite://")
    audit_engine = create_engine("sqlite://")

    create_tables(game_engine=game_engine, audit_engine=audit_engine)

    game_tables = set(inspect(game_engine).get_table_names())
    audit_tables = set(inspect(audit_engine).get_table_names())

    assert game_tables == {model.__tablename__ for model in GAME_TABLE_MODELS}
    assert audit_tables == {model.__tablename__ for model in AUDIT_TABLE_MODELS}
    assert "auditevent" not in game_tables
