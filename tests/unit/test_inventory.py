from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus, GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.models.items import ItemStack
from lorecraft.models.player import Player
from lorecraft.models.world import Item, Room
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.inventory import (
    InventoryService,
    format_inventory_entry,
    format_inventory_summary,
    format_room_items_summary,
    grouped_inventory_ids,
    parse_item_target,
)
from lorecraft.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.engine.game.rng import GameRng
from lorecraft.services.effects import EffectService
from lorecraft.services.meters import MeterService


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
    target = parse_item_target("all")
    assert target.query == ""
    assert target.take_all is True

    target = parse_item_target("everything")
    assert target.query == ""
    assert target.take_all is True

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
        player = _seed_inventory_world(session)
        session.commit()
        _spawn_player_item(session, player.id, "old_sword", quantity=3)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().inventory(ctx)

    assert ctx.messages == [
        "You are carrying: [3] Old Sword.",
    ]
    assert ctx.updates == {
        "inventory": [
            {
                "item_id": "old_sword",
                "name": "Old Sword",
                "quantity": 3,
                "instance_id": None,
            }
        ]
    }


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
        coin = item_repo.get("coin")
        herbs = item_repo.get("herbs")
        assert coin is not None
        assert herbs is not None
        stacks = [
            (
                ItemStack(
                    item_id="coin", owner_type="player", owner_id="p", quantity=2
                ),
                coin,
            ),
            (
                ItemStack(
                    item_id="herbs", owner_type="player", owner_id="p", quantity=1
                ),
                herbs,
            ),
        ]

        summary = format_inventory_summary(stacks)

    assert summary == "[2] Worn Copper Coin, Bundle of Dried Herbs"


def test_format_room_items_summary_groups_room_quantities() -> None:
    coin = Item(id="coin", name="Worn Copper Coin", description="Tarnished.")
    herbs = Item(id="herbs", name="Bundle of Dried Herbs", description="Fragrant.")
    room_items = [
        (
            ItemStack(item_id="coin", owner_type="room", owner_id="tavern", quantity=3),
            coin,
        ),
        (
            ItemStack(
                item_id="herbs", owner_type="room", owner_id="tavern", quantity=1
            ),
            herbs,
        ),
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
        player = _seed_inventory_world(session, sword_in_room=True)
        session.commit()
        bus = EventBus()
        bus.on(GameEvent.ITEM_TAKEN, lambda event, ctx: observed.append(event.payload))
        ctx = _build_context(session, player, bus)

        InventoryService().take_item("old sword", ctx)
        session.commit()
        ctx.flush_events()

        carried = _carried_item_ids(session, "player-1")
        room_stacks = _room_stacks(session, "tavern")

    assert ctx.messages == ["You take Old Sword."]
    assert ctx.room_messages == ["petem takes Old Sword."]
    assert ctx.updates == {
        "inventory": [
            {
                "item_id": "old_sword",
                "name": "Old Sword",
                "quantity": 1,
                "instance_id": None,
            }
        ]
    }
    assert carried == ["old_sword"]
    assert room_stacks == []
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

        carried = _carried_item_ids(session, "player-1")
        room_stack = _room_stacks(session, "market")[0]

    assert ctx.messages == ["You take Bundle of Dried Herbs."]
    assert carried == ["dried_herbs"]
    assert room_stack.quantity == 2


def test_inventory_service_takes_herbs_quantity() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_herbs_world(session, room_quantity=3)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("3 herbs", ctx)
        session.commit()

        carried = _carried_item_ids(session, "player-1")
        room_stacks = _room_stacks(session, "market")

    assert ctx.messages == ["You take [3] Bundle of Dried Herbs."]
    assert carried == ["dried_herbs", "dried_herbs", "dried_herbs"]
    assert room_stacks == []


def test_inventory_service_takes_indexed_herbs() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_herbs_world(session, room_quantity=3)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("2.herbs", ctx)
        session.commit()

        carried = _carried_item_ids(session, "player-1")
        room_stack = _room_stacks(session, "market")[0]

    assert ctx.messages == ["You take Bundle of Dried Herbs."]
    assert carried == ["dried_herbs"]
    assert room_stack.quantity == 2


def test_inventory_service_takes_quantity_and_plural_names() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_coin_world(session, room_quantity=4)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("2 coins", ctx)
        session.commit()

        carried = _carried_item_ids(session, "player-1")
        room_stack = _room_stacks(session, "tavern")[0]

    assert ctx.messages == ["You take [2] Worn Copper Coin."]
    assert carried == ["coin", "coin"]
    assert room_stack.quantity == 2


def test_inventory_service_takes_everything_in_room() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_coin_world(session, room_quantity=3)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("all", ctx)
        session.commit()

        carried = _carried_item_ids(session, "player-1")
        room_stacks = _room_stacks(session, "tavern")

    assert ctx.messages == ["You take [3] Worn Copper Coin."]
    assert carried == ["coin", "coin", "coin"]
    assert room_stacks == []


def test_inventory_service_takes_all_matching_items() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_coin_world(session, room_quantity=3)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("all coin", ctx)
        session.commit()

        carried = _carried_item_ids(session, "player-1")
        room_stacks = _room_stacks(session, "tavern")

    assert ctx.messages == ["You take [3] Worn Copper Coin."]
    assert carried == ["coin", "coin", "coin"]
    assert room_stacks == []


def test_inventory_service_takes_indexed_room_item() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_coin_world(session, room_quantity=3)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().take_item("2.coin", ctx)
        session.commit()

        carried = _carried_item_ids(session, "player-1")
        room_stack = _room_stacks(session, "tavern")[0]

    assert ctx.messages == ["You take Worn Copper Coin."]
    assert carried == ["coin"]
    assert room_stack.quantity == 2


def test_inventory_service_drops_item_back_into_room() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_inventory_world(session)
        session.commit()
        _spawn_player_item(session, player.id, "old_sword")
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().drop_item("old sword", ctx)
        session.commit()

        carried = _carried_item_ids(session, "player-1")
        room_stacks = _room_stacks(session, "tavern")

    assert ctx.messages == ["You drop Old Sword."]
    assert carried == []
    assert [(stack.owner_id, stack.item_id) for stack in room_stacks] == [
        ("tavern", "old_sword")
    ]


def test_inventory_service_drops_quantity_and_all() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_inventory_world(session, include_coin=True)
        session.commit()
        _spawn_player_item(session, player.id, "coin", quantity=3)
        _spawn_player_item(session, player.id, "herbs")
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().drop_item("2 coin", ctx)
        session.commit()

        carried = _carried_item_ids(session, "player-1")
        room_stack = next(
            s for s in _room_stacks(session, "tavern") if s.item_id == "coin"
        )

    assert ctx.messages == ["You drop [2] Worn Copper Coin."]
    assert sorted(carried) == sorted(["coin", "herbs"])
    assert room_stack.quantity == 2

    with Session(engine) as session:
        player = session.get(Player, "player-1")
        assert player is not None
        ctx = _build_context(session, player, EventBus())
        InventoryService().drop_item("all coin", ctx)
        session.commit()
        carried = _carried_item_ids(session, "player-1")

    assert ctx.messages == ["You drop Worn Copper Coin."]
    assert carried == ["herbs"]


def test_inventory_service_drops_indexed_inventory_item() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_inventory_world(session, include_coin=True)
        session.commit()
        _spawn_player_item(session, player.id, "coin", quantity=2)
        _spawn_player_item(session, player.id, "herbs")
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().drop_item("2.coin", ctx)
        session.commit()

        carried = _carried_item_ids(session, "player-1")

    assert ctx.messages == ["You drop Worn Copper Coin."]
    assert sorted(carried) == sorted(["coin", "herbs"])


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
        session.commit()
        _spawn_room_item(session, "tavern", "old_sword")
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
    include_coin: bool = False,
    sword_in_room: bool = False,
) -> Player:
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="tavern",
        respawn_room_id="tavern",
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
        session.add(
            Item(id="herbs", name="Bundle of Dried Herbs", description="Fragrant.")
        )
    session.add(player)
    session.commit()
    if sword_in_room:
        _spawn_room_item(session, "tavern", "old_sword")
        session.commit()
    return player


def _seed_herbs_world(session: Session, *, room_quantity: int) -> Player:
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="market",
        respawn_room_id="market",
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
    session.add(player)
    session.commit()
    _spawn_room_item(session, "market", "dried_herbs", quantity=room_quantity)
    session.commit()
    return player


def _seed_coin_world(session: Session, *, room_quantity: int) -> Player:
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="tavern",
        respawn_room_id="tavern",
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
    session.add(player)
    session.commit()
    _spawn_room_item(session, "tavern", "coin", quantity=room_quantity)
    session.commit()
    return player


def _spawn_room_item(
    session: Session, room_id: str, item_id: str, *, quantity: int = 1
) -> None:
    ItemLocationService(session).spawn(item_id, Location("room", room_id), quantity)


def _spawn_player_item(
    session: Session, player_id: str, item_id: str, *, quantity: int = 1
) -> None:
    ItemLocationService(session).spawn(item_id, Location("player", player_id), quantity)


def _carried_item_ids(session: Session, player_id: str) -> list[str]:
    """Flat, quantity-expanded list of carried item ids (stack creation order)."""
    ids: list[str] = []
    for stack in StackRepo(session).stacks_for_owner("player", player_id):
        ids.extend([stack.item_id] * stack.quantity)
    return ids


def _room_stacks(session: Session, room_id: str) -> list[ItemStack]:
    return StackRepo(session).stacks_at(Location("room", room_id))


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
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=GameRng(),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=bus,
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
