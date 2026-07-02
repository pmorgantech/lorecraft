"""Tests for `export_world_document` — the inverse of `import_world`."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.world.loader import export_world_document, load_world_yaml


def test_export_world_document_round_trips(tmp_path) -> None:
    source = tmp_path / "world.yaml"
    source.write_text(
        """
rooms:
  - id: tavern
    name: Tavern
    description: A warm room.
    map_x: 0
    map_y: 0
    exits:
      - direction: east
        target_room_id: square
        locked: true
        key_item_id: old_sword
  - id: square
    name: Square
    description: A busy square.
    map_x: 1
    map_y: 0
items:
  - id: old_sword
    name: Old Sword
    description: Nicked but serviceable.
    aliases: [sword]
room_items:
  - room_id: tavern
    item_id: old_sword
    quantity: 1
npcs:
  - id: aldric
    name: Aldric
    description: A blacksmith.
    home_room_id: tavern
    dialogue_tree_id: aldric_dialogue
    schedule:
      - game_hour: 8
        target_room_id: square
dialogue_trees:
  - id: aldric_dialogue
    root_node: start
    nodes:
      start:
        text: "Hello there."
        choices:
          - label: "Goodbye"
            next_node: null
quests:
  - id: find_sword
    title: Find the Sword
    description: A simple quest.
    stages:
      - id: stage_1
        description: "Find it"
""",
        encoding="utf-8",
    )
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        load_world_yaml(source, session)
        session.commit()

        document = export_world_document(session)

    assert {r.id for r in document.rooms} == {"tavern", "square"}
    tavern = next(r for r in document.rooms if r.id == "tavern")
    assert len(tavern.exits) == 1
    assert tavern.exits[0].target_room_id == "square"
    assert tavern.exits[0].key_item_id == "old_sword"

    assert {i.id for i in document.items} == {"old_sword"}
    assert document.items[0].aliases == ["sword"]

    assert len(document.room_items) == 1
    assert document.room_items[0].room_id == "tavern"

    assert {n.id for n in document.npcs} == {"aldric"}
    aldric = document.npcs[0]
    assert len(aldric.schedule) == 1
    assert aldric.schedule[0].target_room_id == "square"

    assert {t.id for t in document.dialogue_trees} == {"aldric_dialogue"}
    tree = document.dialogue_trees[0]
    assert tree.root_node == "start"
    assert "start" in tree.nodes
    assert tree.nodes["start"].text == "Hello there."
    assert tree.nodes["start"].choices[0].label == "Goodbye"

    assert {q.id for q in document.quests} == {"find_sword"}
    assert document.quests[0].stages[0].id == "stage_1"
