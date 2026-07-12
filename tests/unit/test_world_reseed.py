"""Unit tests for the shared world wipe + reseed path (Sprint 72.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

from lorecraft.config import Settings
from lorecraft.db import create_tables
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Item, Room
from lorecraft.world.loader import load_world_yaml
from lorecraft.world.reseed import reseed_world_from_yaml, wipe_world
from lorecraft.world.validator import WorldValidationError

_WORLD_V1 = """
rooms:
  - id: square
    name: Square
    description: A busy square.
    map_x: 0
    map_y: 0
  - id: garden
    name: Garden
    description: A quiet garden.
    map_x: 1
    map_y: 0
items:
  - id: coin
    name: Coin
    description: A shiny coin.
room_items:
  - room_id: square
    item_id: coin
    quantity: 1
"""

# A different world: `garden` is gone, `plaza` is new — proves a reseed both
# adds and removes content rather than merely merging.
_WORLD_V2 = """
rooms:
  - id: square
    name: Square
    description: A busy square.
    map_x: 0
    map_y: 0
  - id: plaza
    name: Plaza
    description: A grand plaza.
    map_x: 2
    map_y: 0
items:
  - id: coin
    name: Coin
    description: A shiny coin.
"""

_MALFORMED = """
rooms:
  - id: square
    name: Square
    description: A dangling exit.
    map_x: 0
    map_y: 0
    exits:
      - direction: north
        target_room_id: nowhere
"""


def _make_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def _seed(engine, yaml_text: str, path: Path) -> None:
    path.write_text(yaml_text, encoding="utf-8")
    with Session(engine) as session:
        load_world_yaml(path, session)
        session.commit()


def test_reseed_adds_and_removes_content(tmp_path: Path) -> None:
    engine = _make_engine()
    world = tmp_path / "world.yaml"
    _seed(engine, _WORLD_V1, world)

    world.write_text(_WORLD_V2, encoding="utf-8")
    result = reseed_world_from_yaml(engine, world)

    assert result.rooms == 2
    with Session(engine) as session:
        room_ids = {r.id for r in session.exec(select(Room)).all()}
    # `garden` (only in V1) removed; `plaza` (only in V2) added; `square` kept.
    assert room_ids == {"square", "plaza"}


def test_wipe_world_clears_rooms_and_items(tmp_path: Path) -> None:
    engine = _make_engine()
    world = tmp_path / "world.yaml"
    _seed(engine, _WORLD_V1, world)

    with Session(engine) as session:
        wipe_world(session)
        session.commit()
        assert session.exec(select(Room)).all() == []
        assert session.exec(select(Item)).all() == []


def test_reseed_relocates_stranded_player(tmp_path: Path) -> None:
    engine = _make_engine()
    world = tmp_path / "world.yaml"
    _seed(engine, _WORLD_V1, world)

    # A player standing in `garden`, which the V2 reseed deletes.
    with Session(engine) as session:
        session.add(
            Player(
                id="p1",
                username="p1",
                current_room_id="garden",
                respawn_room_id="garden",
                visited_rooms=["garden"],
            )
        )
        session.commit()

    world.write_text(_WORLD_V2, encoding="utf-8")
    settings = Settings(seed_player_start_room="square")
    result = reseed_world_from_yaml(engine, world, settings=settings)

    assert result.relocated_players == 1
    with Session(engine) as session:
        player = session.get(Player, "p1")
        assert player is not None
        assert player.current_room_id == "square"
        assert player.respawn_room_id == "square"


def test_reseed_leaves_valid_player_in_place(tmp_path: Path) -> None:
    engine = _make_engine()
    world = tmp_path / "world.yaml"
    _seed(engine, _WORLD_V1, world)

    with Session(engine) as session:
        session.add(
            Player(
                id="p1",
                username="p1",
                current_room_id="square",
                respawn_room_id="square",
                visited_rooms=["square"],
            )
        )
        session.commit()

    world.write_text(_WORLD_V2, encoding="utf-8")
    result = reseed_world_from_yaml(
        engine, world, settings=Settings(seed_player_start_room="square")
    )

    assert result.relocated_players == 0
    with Session(engine) as session:
        assert session.get(Player, "p1").current_room_id == "square"  # type: ignore[union-attr]


def test_malformed_yaml_fails_without_wiping(tmp_path: Path) -> None:
    """A malformed world.yaml raises before anything is deleted (validate-first)."""
    engine = _make_engine()
    world = tmp_path / "world.yaml"
    _seed(engine, _WORLD_V1, world)

    world.write_text(_MALFORMED, encoding="utf-8")
    with pytest.raises(WorldValidationError):
        reseed_world_from_yaml(engine, world)

    # Original content is untouched — no half-apply.
    with Session(engine) as session:
        room_ids = {r.id for r in session.exec(select(Room)).all()}
    assert room_ids == {"square", "garden"}
