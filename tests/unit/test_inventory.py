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
from lorecraft.services.inventory import InventoryService


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


def test_inventory_service_look_lists_exits_and_items() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = _seed_inventory_world(session)
        session.commit()
        ctx = _build_context(session, player, EventBus())

        InventoryService().look(ctx)

    assert ctx.messages == [
        "Tavern",
        "A warm room.",
        "There are no obvious exits.",
        "You see: Old Sword.",
    ]
    assert ctx.updates == {"room_id": "tavern"}


def _seed_inventory_world(
    session: Session, *, inventory: list[str] | None = None
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
    if not inventory:
        session.add(RoomItem(room_id="tavern", item_id="old_sword"))
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
