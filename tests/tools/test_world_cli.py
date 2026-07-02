"""Tests for the world_cli import/export/validate/diff/merge/stats commands."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import yaml
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.tools import world_cli
from lorecraft.world.loader import load_world_yaml

_SAMPLE_WORLD = """
rooms:
  - id: tavern
    name: Tavern
    description: A warm room.
    map_x: 0
    map_y: 0
    exits:
      - direction: east
        target_room_id: square
  - id: square
    name: Square
    description: A busy square.
    map_x: 1
    map_y: 0
items:
  - id: old_sword
    name: Old Sword
    description: Nicked but serviceable.
room_items:
  - room_id: tavern
    item_id: old_sword
    quantity: 1
"""


def _run(args: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = world_cli.main(args)
    return code, buf.getvalue()


def test_import_and_stats_round_trip(tmp_path) -> None:
    world_file = tmp_path / "world.yaml"
    world_file.write_text(_SAMPLE_WORLD, encoding="utf-8")
    db_path = tmp_path / "game.db"

    code, out = _run(
        ["import", "--file", str(world_file), "--db", str(db_path), "--fresh"]
    )
    assert code == 0
    assert "2 rooms" in out
    assert "1 items" in out

    code, out = _run(["stats", "--db", str(db_path)])
    assert code == 0
    assert "rooms:          2" in out
    assert "items:          1" in out
    assert "room_items:     1" in out


def test_export_yaml_round_trips_through_import(tmp_path) -> None:
    world_file = tmp_path / "world.yaml"
    world_file.write_text(_SAMPLE_WORLD, encoding="utf-8")
    db_path = tmp_path / "game.db"
    _run(["import", "--file", str(world_file), "--db", str(db_path), "--fresh"])

    export_path = tmp_path / "exported.yaml"
    code, out = _run(["export", "--db", str(db_path), "--output", str(export_path)])
    assert code == 0
    assert export_path.is_file()

    # The exported document imports cleanly into a fresh DB.
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        document = load_world_yaml(export_path, session)
        assert len(document.rooms) == 2
        assert len(document.items) == 1


def test_export_json_format(tmp_path) -> None:
    world_file = tmp_path / "world.yaml"
    world_file.write_text(_SAMPLE_WORLD, encoding="utf-8")
    db_path = tmp_path / "game.db"
    _run(["import", "--file", str(world_file), "--db", str(db_path), "--fresh"])

    export_path = tmp_path / "exported.json"
    code, _out = _run(
        [
            "export",
            "--db",
            str(db_path),
            "--output",
            str(export_path),
            "--format",
            "json",
        ]
    )
    assert code == 0
    data = json.loads(export_path.read_text())
    assert len(data["rooms"]) == 2


def test_validate_valid_file(tmp_path) -> None:
    world_file = tmp_path / "world.yaml"
    world_file.write_text(_SAMPLE_WORLD, encoding="utf-8")

    code, out = _run(["validate", "--file", str(world_file)])
    assert code == 0
    assert "Schema valid" in out


def test_validate_rejects_broken_reference(tmp_path) -> None:
    world_file = tmp_path / "world.yaml"
    world_file.write_text(
        """
rooms:
  - id: tavern
    name: Tavern
    description: A warm room.
    map_x: 0
    map_y: 0
    exits:
      - direction: east
        target_room_id: nonexistent_room
""",
        encoding="utf-8",
    )

    code, out = _run(["validate", "--file", str(world_file)])
    assert code == 1
    assert "nonexistent_room" in out


def test_diff_reports_added_and_removed_rooms(tmp_path) -> None:
    from_file = tmp_path / "from.yaml"
    from_file.write_text(_SAMPLE_WORLD, encoding="utf-8")

    to_file = tmp_path / "to.yaml"
    to_data = yaml.safe_load(_SAMPLE_WORLD)
    to_data["rooms"].append(
        {
            "id": "cellar",
            "name": "Cellar",
            "description": "Dark and damp.",
            "map_x": 0,
            "map_y": -1,
        }
    )
    to_data["rooms"] = [r for r in to_data["rooms"] if r["id"] != "square"]
    to_data["rooms"][0]["exits"] = []  # drop the now-dangling tavern -> square exit
    to_file.write_text(yaml.safe_dump(to_data), encoding="utf-8")

    output_file = tmp_path / "diff.yaml"
    code, _out = _run(
        [
            "diff",
            "--from",
            str(from_file),
            "--to",
            str(to_file),
            "--output",
            str(output_file),
        ]
    )
    assert code == 0
    result = yaml.safe_load(output_file.read_text())
    assert result["rooms"]["added"] == ["cellar"]
    assert result["rooms"]["removed"] == ["square"]


def test_merge_theirs_wins_on_collision(tmp_path) -> None:
    base_file = tmp_path / "base.yaml"
    base_file.write_text(_SAMPLE_WORLD, encoding="utf-8")

    theirs_file = tmp_path / "theirs.yaml"
    theirs_data = yaml.safe_load(_SAMPLE_WORLD)
    theirs_data["rooms"][0]["name"] = "Renovated Tavern"
    theirs_data["rooms"] = [r for r in theirs_data["rooms"] if r["id"] != "square"]
    theirs_data["rooms"][0]["exits"] = []  # drop the now-dangling tavern -> square exit
    theirs_file.write_text(yaml.safe_dump(theirs_data), encoding="utf-8")

    output_file = tmp_path / "merged.yaml"
    code, _out = _run(
        [
            "merge",
            "--base",
            str(base_file),
            "--theirs",
            str(theirs_file),
            "--output",
            str(output_file),
        ]
    )
    assert code == 0
    merged = yaml.safe_load(output_file.read_text())
    room_ids = {r["id"] for r in merged["rooms"]}
    # base-only room ("square") is kept even though theirs dropped it
    assert room_ids == {"tavern", "square"}
    tavern = next(r for r in merged["rooms"] if r["id"] == "tavern")
    assert tavern["name"] == "Renovated Tavern"


def test_import_fresh_wipes_existing_world_content(tmp_path) -> None:
    world_file = tmp_path / "world.yaml"
    world_file.write_text(_SAMPLE_WORLD, encoding="utf-8")
    db_path = tmp_path / "game.db"
    _run(["import", "--file", str(world_file), "--db", str(db_path), "--fresh"])

    smaller_world = """
rooms:
  - id: solo_room
    name: Solo Room
    description: Just one room.
    map_x: 0
    map_y: 0
"""
    smaller_file = tmp_path / "smaller.yaml"
    smaller_file.write_text(smaller_world, encoding="utf-8")
    _run(["import", "--file", str(smaller_file), "--db", str(db_path), "--fresh"])

    code, out = _run(["stats", "--db", str(db_path)])
    assert code == 0
    assert "rooms:          1" in out
    assert "items:          0" in out
