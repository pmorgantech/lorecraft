from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.holders import Location
from lorecraft.models.player import Player
from lorecraft.models.world import Item
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.web.session import inventory_snapshot


def test_inventory_snapshot_groups_duplicate_items() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        session.add(
            Item(
                id="apple",
                name="Apple",
                description="A crisp red apple.",
            )
        )
        session.add(
            Item(
                id="bread",
                name="Bread",
                description="A loaf of bread.",
            )
        )
        player = Player(
            id="player-1",
            username="petem",
            current_room_id="tavern",
            respawn_room_id="tavern",
        )
        session.add(player)
        session.commit()
        item_location = ItemLocationService(session)
        item_location.spawn("apple", Location("player", player.id), 3)
        item_location.spawn("bread", Location("player", player.id), 1)
        session.commit()

        snapshot = inventory_snapshot(player, ItemRepo(session))

    assert snapshot == [
        {
            "id": "apple",
            "name": "Apple",
            "description_short": "A crisp red apple.",
            "quantity": 3,
            "usable": False,
            "droppable": True,
        },
        {
            "id": "bread",
            "name": "Bread",
            "description_short": "A loaf of bread.",
            "quantity": 1,
            "usable": False,
            "droppable": True,
        },
    ]
