"""Tests for the Tier 2 progression config: YAML seeding + export round-trip."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.features.progression.repo import ProgressionRepo
from lorecraft.world.loader import export_world_document, load_world_yaml

_WORLD_WITH_PROGRESSION = """
rooms:
  - id: start
    name: Start
    description: The beginning.
    map_x: 0
    map_y: 0
progression:
  base: 120
  step: 40
  coins_per_level: 30
  skill_points_per_level: 2
"""

_WORLD_WITHOUT_PROGRESSION = """
rooms:
  - id: start
    name: Start
    description: The beginning.
    map_x: 0
    map_y: 0
"""


def _load(text: str, tmp_path) -> Session:
    source = tmp_path / "world.yaml"
    source.write_text(text, encoding="utf-8")
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    load_world_yaml(source, session)
    session.commit()
    return session


def test_progression_config_seeds_from_yaml(tmp_path) -> None:
    with _load(_WORLD_WITH_PROGRESSION, tmp_path) as session:
        config = ProgressionRepo(session).config()
        assert config is not None
        assert config.base == 120
        assert config.step == 40
        assert config.coins_per_level == 30
        assert config.skill_points_per_level == 2


def test_progression_config_absent_when_yaml_omits_section(tmp_path) -> None:
    with _load(_WORLD_WITHOUT_PROGRESSION, tmp_path) as session:
        assert ProgressionRepo(session).config() is None


def test_progression_config_round_trips_via_export(tmp_path) -> None:
    with _load(_WORLD_WITH_PROGRESSION, tmp_path) as session:
        document = export_world_document(session)
    assert document.progression is not None
    assert document.progression.base == 120
    assert document.progression.step == 40
    assert document.progression.coins_per_level == 30
    assert document.progression.skill_points_per_level == 2


def test_progression_config_reimport_upserts_single_row(tmp_path) -> None:
    # A second import (e.g. reseed with edited numbers) updates the row in place
    # rather than stacking a duplicate singleton.
    with _load(_WORLD_WITH_PROGRESSION, tmp_path) as session:
        source = tmp_path / "world.yaml"
        source.write_text(
            _WORLD_WITH_PROGRESSION.replace(
                "coins_per_level: 30", "coins_per_level: 99"
            ),
            encoding="utf-8",
        )
        load_world_yaml(source, session)
        session.commit()

        from lorecraft.features.progression.models import ProgressionConfig
        from sqlmodel import select

        rows = session.exec(select(ProgressionConfig)).all()
        assert len(rows) == 1
        assert rows[0].coins_per_level == 99
