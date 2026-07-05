import pytest
from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.features.bank.models import Bank
from lorecraft.features.economy.models import RegionPricing, Shop, ShopStock
from lorecraft.engine.models.items import ItemStack
from lorecraft.models.transit import TransitLine, TransitStop
from lorecraft.engine.models.world import Exit, Item, Room
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


def test_world_loader_imports_npc_bank_branch(tmp_path) -> None:
    source = tmp_path / "world.yaml"
    source.write_text(
        """
rooms:
  - id: tavern
    name: Tavern
    description: A warm room.
    map_x: 0
    map_y: 0
npcs:
  - id: teller
    name: Teller
    description: Counts coins.
    home_room_id: tavern
    bank:
      name: "Saltmarsh Bank"
""",
        encoding="utf-8",
    )
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        load_world_yaml(source, session)
        session.commit()

        bank = session.exec(select(Bank).where(Bank.npc_id == "teller")).first()
        assert bank is not None and bank.name == "Saltmarsh Bank"

        document = export_world_document(session)
        assert document.npcs[0].bank is not None
        assert document.npcs[0].bank.name == "Saltmarsh Bank"


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


def _transit_world_yaml(*, stops: str) -> str:
    return f"""
rooms:
  - id: pier
    name: Pier
    description: A weathered pier.
    map_x: 0
    map_y: 0
  - id: rock
    name: Gull Rock
    description: A rocky islet.
    map_x: 2
    map_y: 1
  - id: ferry_deck
    name: Ferry Deck
    description: The deck of the ferry.
    map_x: 0
    map_y: 0
items:
  - id: ferry_token
    name: Ferry Token
    description: A brass token.
npcs: []
transit:
  lines:
    - id: coastal_ferry
      name: Coastal Ferry
      mode: ferry
      service_type: local
      vehicle_room_id: ferry_deck
      ticket_item_id: ferry_token
      weather_sensitive: true
      blocking_weather: [fog]
      stops:
{stops}
"""


_VALID_STOPS = """\
        - { room_id: pier, sequence: 0, dwell_ticks: 5, travel_ticks: 20 }
        - { room_id: rock, sequence: 1, dwell_ticks: 8, travel_ticks: 0 }
"""


def test_world_loader_imports_transit_line(tmp_path) -> None:
    source = tmp_path / "world.yaml"
    source.write_text(_transit_world_yaml(stops=_VALID_STOPS), encoding="utf-8")
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        load_world_yaml(source, session)
        session.commit()

        line = session.get(TransitLine, "coastal_ferry")
        assert line is not None
        assert line.mode == "ferry"
        assert line.blocking_weather == ["fog"]
        stops = session.exec(
            select(TransitStop)
            .where(TransitStop.line_id == "coastal_ferry")
            .order_by(TransitStop.sequence)  # type: ignore[arg-type]
        ).all()
        assert [s.room_id for s in stops] == ["pier", "rock"]

        document = export_world_document(session)
        assert document.transit is not None
        assert document.transit.lines[0].id == "coastal_ferry"
        assert [s.room_id for s in document.transit.lines[0].stops] == ["pier", "rock"]


def test_world_loader_reimport_removes_stale_stops(tmp_path) -> None:
    source = tmp_path / "world.yaml"
    source.write_text(_transit_world_yaml(stops=_VALID_STOPS), encoding="utf-8")
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        load_world_yaml(source, session)
        session.commit()

    shrunk = tmp_path / "world2.yaml"
    shrunk.write_text(
        _transit_world_yaml(
            stops="        - { room_id: pier, sequence: 0, dwell_ticks: 5, travel_ticks: 0 }\n"
        ),
        encoding="utf-8",
    )
    with Session(engine) as session:
        load_world_yaml(shrunk, session)
        session.commit()
        stops = session.exec(
            select(TransitStop).where(TransitStop.line_id == "coastal_ferry")
        ).all()
        assert [s.room_id for s in stops] == ["pier"]


def test_world_validator_rejects_vehicle_room_with_exits() -> None:
    with pytest.raises(WorldValidationError, match="no static exits"):
        validate_world_document(
            {
                "rooms": [
                    {
                        "id": "pier",
                        "name": "Pier",
                        "description": "d",
                        "map_x": 0,
                        "map_y": 0,
                    },
                    {
                        "id": "ferry_deck",
                        "name": "Ferry Deck",
                        "description": "d",
                        "map_x": 0,
                        "map_y": 0,
                        "exits": [{"direction": "east", "target_room_id": "pier"}],
                    },
                ],
                "transit": {
                    "lines": [
                        {
                            "id": "line1",
                            "name": "Line",
                            "mode": "ferry",
                            "vehicle_room_id": "ferry_deck",
                            "stops": [
                                {"room_id": "pier", "sequence": 0},
                            ],
                        }
                    ]
                },
            }
        )


def test_world_validator_rejects_noncontiguous_sequences() -> None:
    with pytest.raises(WorldValidationError, match="contiguous"):
        validate_world_document(
            {
                "rooms": [
                    {
                        "id": "pier",
                        "name": "Pier",
                        "description": "d",
                        "map_x": 0,
                        "map_y": 0,
                    },
                    {
                        "id": "rock",
                        "name": "Rock",
                        "description": "d",
                        "map_x": 1,
                        "map_y": 0,
                    },
                ],
                "transit": {
                    "lines": [
                        {
                            "id": "line1",
                            "name": "Line",
                            "mode": "ferry",
                            "stops": [
                                {"room_id": "pier", "sequence": 0},
                                {"room_id": "rock", "sequence": 2},
                            ],
                        }
                    ]
                },
            }
        )


def test_world_validator_rejects_express_line_with_too_few_boarding_stops() -> None:
    with pytest.raises(WorldValidationError, match="express but has fewer"):
        validate_world_document(
            {
                "rooms": [
                    {
                        "id": "pier",
                        "name": "Pier",
                        "description": "d",
                        "map_x": 0,
                        "map_y": 0,
                    },
                    {
                        "id": "rock",
                        "name": "Rock",
                        "description": "d",
                        "map_x": 1,
                        "map_y": 0,
                    },
                ],
                "transit": {
                    "lines": [
                        {
                            "id": "line1",
                            "name": "Line",
                            "mode": "ferry",
                            "service_type": "express",
                            "stops": [
                                {"room_id": "pier", "sequence": 0, "boarding": True},
                                {"room_id": "rock", "sequence": 1, "boarding": False},
                            ],
                        }
                    ]
                },
            }
        )


def test_world_validator_rejects_unknown_blocking_weather() -> None:
    with pytest.raises(WorldValidationError, match="unknown state"):
        validate_world_document(
            {
                "rooms": [
                    {
                        "id": "pier",
                        "name": "Pier",
                        "description": "d",
                        "map_x": 0,
                        "map_y": 0,
                    },
                ],
                "transit": {
                    "lines": [
                        {
                            "id": "line1",
                            "name": "Line",
                            "mode": "ferry",
                            "blocking_weather": ["meteor_shower"],
                            "stops": [{"room_id": "pier", "sequence": 0}],
                        }
                    ]
                },
            }
        )
