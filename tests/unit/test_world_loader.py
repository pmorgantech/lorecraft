import pytest
from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.models.items import ItemStack
from lorecraft.models.world import Exit, Item, Room
from lorecraft.world.loader import load_world_yaml
from lorecraft.world.validator import WorldValidationError, validate_world_document


def test_world_loader_imports_valid_yaml(tmp_path) -> None:
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
room_items:
  - room_id: tavern
    item_id: old_sword
    quantity: 1
""",
        encoding="utf-8",
    )
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        document = load_world_yaml(source, session)
        session.commit()

        rooms = session.exec(select(Room)).all()
        exits = session.exec(select(Exit)).all()
        items = session.exec(select(Item)).all()
        room_stacks = session.exec(
            select(ItemStack).where(ItemStack.owner_type == "room")
        ).all()

    assert [room.id for room in document.rooms] == ["tavern", "square"]
    assert {room.id for room in rooms} == {"square", "tavern"}
    assert [
        (exit_.room_id, exit_.direction, exit_.target_room_id) for exit_ in exits
    ] == [("tavern", "east", "square")]
    assert [item.id for item in items] == ["old_sword"]
    assert [(stack.owner_id, stack.item_id) for stack in room_stacks] == [
        ("tavern", "old_sword")
    ]


def test_world_validator_rejects_missing_exit_target() -> None:
    with pytest.raises(WorldValidationError, match="missing room square"):
        validate_world_document(
            {
                "rooms": [
                    {
                        "id": "tavern",
                        "name": "Tavern",
                        "description": "A warm room.",
                        "map_x": 0,
                        "map_y": 0,
                        "exits": [{"direction": "east", "target_room_id": "square"}],
                    }
                ]
            }
        )
