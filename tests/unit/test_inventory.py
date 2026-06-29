from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.events import EventBus, GameEvent
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player
from lorecraft.models.world import Item, Room, RoomItem
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.services.inventory import (
    InventoryService,
    format_inventory_entry,
    format_inventory_summary,
    format_room_items_summary,
    grouped_inventory_ids,
    parse_item_target,
)


def test_format_inventory_entry_shows_quantity_prefix() -> None:
    assert format_inventory_entry("Worn Copper Coin", 1) == "Worn Copper Coin"
    assert format_inventory_entry("Worn Copper Coin", 2) == "[2] Worn Copper Coin"


def test_grouped_inventory_ids_preserves_order_and_counts() -> None:
    assert grouped_inventory_ids([]) == []
    assert grouped_inventory_ids(["apple"]) == [("apple", 1)]
    assert grouped_inventory_ids(["apple", "bread", "apple", "apple"]) == [
        ("apple", 3),
        ("bread", 1),
    ]


def test_parse_item_target_supports_quantity_all_and_index() -> None:
    target = parse_item_target("all coin")
    assert target.query == "coin"
    assert target.take_all is True

    target = parse_item_target("2 coin")
    assert target.query == "coin"
    assert target.quantity == 2
    assert target.index is None

    target = parse_item_target("2 coins")
    assert target.query == "coins"
    assert target.quantity == 2

    target = parse_item_target("2.coin")
    assert target.query == "coin"
    assert target.index == 2

    target = parse_item_target("3. worn copper coin")
    assert target.query == "worn copper coin"
    assert target.index == 3


def test_inventory_service_lists_grouped_quantities() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_inventory_world(
            session,
            inventory=["old_sword", "old_sword", "old_sword"],
        )
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().inventory(ctx)

    assert ctx.messages == [
        "You are carrying: [3] Old Sword.",
    ]
    assert ctx.updates == {"inventory": ["old_sword", "old_sword", "old_sword"]}


def test_format_inventory_summary_groups_mixed_items() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        session.add(Item(id="coin", name="Worn Copper Coin", description="Tarnished."))
        session.add(
            Item(id="herbs", name="Bundle of Dried Herbs", description="Fragrant.")
        )
        session.commit()
        item_repo = ItemRepo(session)

        summary = format_inventory_summary(
            ["coin", "herbs", "coin"],
            item_repo.get,
        )

    assert summary == "[2] Worn Copper Coin, Bundle of Dried Herbs"


def test_format_room_items_summary_groups_room_quantities() -> None:
    coin = Item(id="coin", name="Worn Copper Coin", description="Tarnished.")
    herbs = Item(id="herbs", name="Bundle of Dried Herbs", description="Fragrant.")
    room_items = [
        (RoomItem(room_id="tavern", item_id="coin", quantity=3), coin),
        (RoomItem(room_id="tavern", item_id="herbs", quantity=1), herbs),
    ]

    assert (
        format_room_items_summary(room_items)
        == "Bundle of Dried Herbs, [3] Worn Copper Coin"
    )


def test_inventory_service_takes_item_and_queues_event() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    observed = []

    with Session(engine) as session:
        player = _seed_inventory_world(session)
        session.commit()
        bus = EventBus()
        bus.on(GameEvent.ITEM_TAKEN, lambda event, ctx: observed.append(event.payload))
        ctx = _build_context(session, player, bus)

        InventoryService().take_item("old sword", ctx)
        session.commit()
        ctx.flush_events()

        persisted = session.get(Player, "player-1")
        room_items = session.exec(select(RoomItem)).all()

    assert ctx.messages == ["You take Old Sword."]
    assert ctx.room_messages == ["petem takes Old Sword."]
    assert ctx.updates == {"inventory": ["old_sword"]}
    assert persisted is not None
    assert persisted.inventory == ["old_sword"]
    assert room_items == []
    assert observed == [
        {"player_id": "player-1", "room_id": "tavern", "item_id": "old_sword"}
    ]


def test_inventory_service_takes_herbs_by_plural_name() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_herbs_world(session, room_quantity=3)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("herbs", ctx)
        session.commit()

        persisted = session.get(Player, "player-1")
        room_item = session.exec(select(RoomItem)).one()

    assert ctx.messages == ["You take Bundle of Dried Herbs."]
    assert persisted is not None
    assert persisted.inventory == ["dried_herbs"]
    assert room_item.quantity == 2


def test_inventory_service_takes_herbs_quantity() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_herbs_world(session, room_quantity=3)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("3 herbs", ctx)
        session.commit()

        persisted = session.get(Player, "player-1")
        room_items = session.exec(select(RoomItem)).all()

    assert ctx.messages == ["You take [3] Bundle of Dried Herbs."]
    assert persisted is not None
    assert persisted.inventory == ["dried_herbs", "dried_herbs", "dried_herbs"]
    assert room_items == []


def test_inventory_service_takes_indexed_herbs() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_herbs_world(session, room_quantity=3)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("2.herbs", ctx)
        session.commit()

        persisted = session.get(Player, "player-1")
        room_item = session.exec(select(RoomItem)).one()

    assert ctx.messages == ["You take Bundle of Dried Herbs."]
    assert persisted is not None
    assert persisted.inventory == ["dried_herbs"]
    assert room_item.quantity == 2


def test_inventory_service_takes_quantity_and_plural_names() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_coin_world(session, room_quantity=4)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("2 coins", ctx)
        session.commit()

        persisted = session.get(Player, "player-1")
        room_item = session.exec(select(RoomItem)).one()

    assert ctx.messages == ["You take [2] Worn Copper Coin."]
    assert persisted is not None
    assert persisted.inventory == ["coin", "coin"]
    assert room_item.quantity == 2


def test_inventory_service_takes_all_matching_items() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_coin_world(session, room_quantity=3)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("all coin", ctx)
        session.commit()

        persisted = session.get(Player, "player-1")
        room_items = session.exec(select(RoomItem)).all()

    assert ctx.messages == ["You take [3] Worn Copper Coin."]
    assert persisted is not None
    assert persisted.inventory == ["coin", "coin", "coin"]
    assert room_items == []


def test_inventory_service_takes_indexed_room_item() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_coin_world(session, room_quantity=3)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("2.coin", ctx)
        session.commit()

        persisted = session.get(Player, "player-1")
        room_item = session.exec(select(RoomItem)).one()

    assert ctx.messages == ["You take Worn Copper Coin."]
    assert persisted is not None
    assert persisted.inventory == ["coin"]
    assert room_item.quantity == 2


def test_inventory_service_drops_item_back_into_room() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_inventory_world(session, inventory=["old_sword"])
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().drop_item("old sword", ctx)
        session.commit()

        persisted = session.get(Player, "player-1")
        room_items = session.exec(select(RoomItem)).all()

    assert ctx.messages == ["You drop Old Sword."]
    assert persisted is not None
    assert persisted.inventory == []
    assert [(room_item.room_id, room_item.item_id) for room_item in room_items] == [
        ("tavern", "old_sword")
    ]


def test_inventory_service_drops_quantity_and_all() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_inventory_world(
            session,
            inventory=["coin", "coin", "coin", "herbs"],
            include_coin=True,
        )
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().drop_item("2 coin", ctx)
        session.commit()

        persisted = session.get(Player, "player-1")
        room_item = session.exec(
            select(RoomItem).where(RoomItem.item_id == "coin")
        ).one()

    assert ctx.messages == ["You drop [2] Worn Copper Coin."]
    assert persisted is not None
    assert persisted.inventory == ["coin", "herbs"]
    assert room_item.quantity == 2

    with Session(engine) as session:
        player = session.get(Player, "player-1")
        assert player is not None
        ctx = _build_context(session, player, EventBus())
        InventoryService().drop_item("all coin", ctx)
        session.commit()
        persisted = session.get(Player, "player-1")

    assert ctx.messages == ["You drop Worn Copper Coin."]
    assert persisted is not None
    assert persisted.inventory == ["herbs"]


def test_inventory_service_drops_indexed_inventory_item() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_inventory_world(
            session,
            inventory=["coin", "herbs", "coin"],
            include_coin=True,
        )
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().drop_item("2.coin", ctx)
        session.commit()

        persisted = session.get(Player, "player-1")

    assert ctx.messages == ["You drop Worn Copper Coin."]
    assert persisted is not None
    assert persisted.inventory == ["coin", "herbs"]


def test_inventory_service_look_lists_exits_and_grouped_items() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_coin_world(session, room_quantity=2)
        session.add(
            Item(
                id="old_sword", name="Old Sword", description="Nicked but serviceable."
            )
        )
        session.add(
            RoomItem(room_id="tavern", item_id="old_sword", quantity=1),
        )
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().look(ctx)

    assert ctx.messages == [
        "Tavern",
        "A warm room.",
        "There are no obvious exits.",
        "You see: Old Sword, [2] Worn Copper Coin.",
    ]
    assert ctx.updates == {"room_id": "tavern"}


def _seed_inventory_world(
    session: Session,
    *,
    inventory: list[str] | None = None,
    include_coin: bool = False,
) -> Player:
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="tavern",
        respawn_room_id="tavern",
        inventory=inventory or [],
    )
    session.add(
        Room(
            id="tavern",
            name="Tavern",
            description="A warm room.",
            map_x=0,
            map_y=0,
        )
    )
    session.add(
        Item(id="old_sword", name="Old Sword", description="Nicked but serviceable.")
    )
    if include_coin:
        session.add(Item(id="coin", name="Worn Copper Coin", description="Tarnished."))
    if not inventory:
        session.add(RoomItem(room_id="tavern", item_id="old_sword"))
    session.add(player)
    return player


def _seed_herbs_world(session: Session, *, room_quantity: int) -> Player:
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="market",
        respawn_room_id="market",
        inventory=[],
    )
    session.add(
        Room(
            id="market",
            name="Market",
            description="Busy stalls.",
            map_x=0,
            map_y=0,
        )
    )
    session.add(
        Item(
            id="dried_herbs",
            name="Bundle of Dried Herbs",
            description="Fragrant.",
            takeable=True,
        )
    )
    session.add(
        RoomItem(room_id="market", item_id="dried_herbs", quantity=room_quantity),
    )
    session.add(player)
    return player


def _seed_coin_world(session: Session, *, room_quantity: int) -> Player:
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="tavern",
        respawn_room_id="tavern",
        inventory=[],
    )
    session.add(
        Room(
            id="tavern",
            name="Tavern",
            description="A warm room.",
            map_x=0,
            map_y=0,
        )
    )
    session.add(Item(id="coin", name="Worn Copper Coin", description="Tarnished."))
    session.add(
        RoomItem(room_id="tavern", item_id="coin", quantity=room_quantity),
    )
    session.add(player)
    return player


def _build_context(session: Session, player: Player, bus: EventBus) -> GameContext:
    room = session.get(Room, player.current_room_id)
    assert room is not None
    return GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=bus,
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
