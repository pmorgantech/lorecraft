import pytest
from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.models.economy import RegionPricing, Shop, ShopStock
from lorecraft.models.items import ItemStack
from lorecraft.models.world import Exit, Item, Room
from lorecraft.repos.ledger_repo import LedgerRepo
from lorecraft.world.loader import export_world_document, load_world_yaml
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


def test_world_loader_imports_npc_shop_and_seeds_cash_once(tmp_path) -> None:
    source = tmp_path / "world.yaml"
    source.write_text(
        """
rooms:
  - id: tavern
    name: Tavern
    description: A warm room.
    map_x: 0
    map_y: 0
items:
  - id: salt_sack
    name: Sack of Salt
    description: Coarse and grey.
    value: 20
    tradeable: true
    category: trade_good
npcs:
  - id: shopkeep
    name: Shopkeep
    description: Sells things.
    home_room_id: tavern
    shop:
      name: General Store
      buys_categories: [trade_good]
      sell_ratio: 0.5
      starting_coins: 300
      stock:
        - item_id: salt_sack
          quantity: 10
""",
        encoding="utf-8",
    )
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        load_world_yaml(source, session)
        session.commit()

        shop = session.exec(select(Shop).where(Shop.npc_id == "shopkeep")).first()
        assert shop is not None
        assert shop.name == "General Store"
        stock = session.exec(
            select(ShopStock).where(ShopStock.shop_id == shop.id)
        ).all()
        assert [(s.item_id, s.quantity) for s in stock] == [("salt_sack", 10)]
        balance = LedgerRepo(session).find("shop", shop.id)
        assert balance is not None and balance.balance == 300

        # Re-importing the same document must not double-credit the shop.
        load_world_yaml(source, session)
        session.commit()
        balance_again = LedgerRepo(session).find("shop", shop.id)
        assert balance_again is not None and balance_again.balance == 300

        document = export_world_document(session)
        assert document.npcs[0].shop is not None
        assert document.npcs[0].shop.starting_coins == 300
        assert [s.item_id for s in document.npcs[0].shop.stock] == ["salt_sack"]


def test_world_loader_imports_regional_pricing(tmp_path) -> None:
    source = tmp_path / "world.yaml"
    source.write_text(
        """
rooms:
  - id: coastal_market
    name: Coastal Market
    description: Salt air and gulls.
    map_x: 0
    map_y: 0
    area_id: coast
items:
  - id: salt_sack
    name: Sack of Salt
    description: Coarse and grey.
    value: 20
    tradeable: true
economy:
  regions:
    - area_id: coast
      region_mult: 0.8
      bias: { salt_sack: 0.5 }
""",
        encoding="utf-8",
    )
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        load_world_yaml(source, session)
        session.commit()

        region = session.get(RegionPricing, "coast")
        assert region is not None
        assert region.region_mult == 0.8
        assert region.bias == {"salt_sack": 0.5}

        document = export_world_document(session)
        assert document.economy is not None
        assert document.economy.regions[0].area_id == "coast"
        assert document.economy.regions[0].bias == {"salt_sack": 0.5}


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


def test_world_validator_rejects_region_with_missing_area_id() -> None:
    with pytest.raises(WorldValidationError, match="missing area_id"):
        validate_world_document(
            {
                "rooms": [
                    {
                        "id": "tavern",
                        "name": "Tavern",
                        "description": "A warm room.",
                        "map_x": 0,
                        "map_y": 0,
                        "area_id": "town",
                    }
                ],
                "economy": {"regions": [{"area_id": "highlands"}]},
            }
        )
