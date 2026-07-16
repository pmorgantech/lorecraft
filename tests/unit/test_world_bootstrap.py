"""Unit tests for YAML-driven world bootstrap."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from lorecraft.config import Settings
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room
from lorecraft.world.bootstrap import (
    align_default_respawn_rooms,
    ensure_world_bootstrapped,
    resolve_world_yaml_path,
)


def test_resolve_world_yaml_path_finds_repo_world() -> None:
    path = resolve_world_yaml_path("world_content/world.yaml")
    assert path.is_file()
    assert path.name == "world.yaml"


def test_resolve_world_yaml_path_accepts_repo_world_directory() -> None:
    path = resolve_world_yaml_path("world_content")
    assert path.is_file()
    assert path.name == "world.yaml"


def test_ensure_world_bootstrapped_imports_yaml_and_seeds_player() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        world_yaml_path="world_content/world.yaml",
        seed_player_start_room="village_square",
    )
    from lorecraft.db import create_tables

    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    ensure_world_bootstrapped(engine, settings)

    with Session(engine) as session:
        rooms = session.exec(select(Room)).all()
        player = session.get(Player, "player-1")

    assert len(rooms) >= 19
    assert player is not None
    assert player.current_room_id == "village_square"
    assert player.respawn_room_id == "ashmoore_recall_sanctum"
    assert Path(settings.world_yaml_path).name == "world.yaml"


def test_align_default_respawn_rooms_preserves_custom_respawn() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        seed_player_start_room="village_square",
        seed_player_respawn_room="ashmoore_recall_sanctum",
    )
    from lorecraft.db import create_tables

    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        session.add(
            Room(
                id="village_square",
                name="Village Square",
                description="Start.",
                map_x=0,
                map_y=0,
            )
        )
        session.add(
            Room(
                id="ashmoore_recall_sanctum",
                name="Recall Sanctum",
                description="Safe.",
                map_x=0,
                map_y=0,
                map_z=-1,
            )
        )
        session.add(
            Room(id="temple", name="Temple", description="Custom.", map_x=1, map_y=1)
        )
        session.add(
            Player(
                id="legacy",
                username="legacy",
                current_room_id="village_square",
                respawn_room_id="village_square",
            )
        )
        session.add(
            Player(
                id="custom",
                username="custom",
                current_room_id="village_square",
                respawn_room_id="temple",
            )
        )
        session.commit()

        assert align_default_respawn_rooms(session, settings) == 1
        session.commit()

        legacy = session.get(Player, "legacy")
        custom = session.get(Player, "custom")
        assert legacy is not None
        assert custom is not None
        assert legacy.respawn_room_id == "ashmoore_recall_sanctum"
        assert custom.respawn_room_id == "temple"
