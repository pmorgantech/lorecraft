from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.events import EventBus, GameEvent
from lorecraft.game.holders import Location
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player
from lorecraft.models.world import Exit, Item, Room
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.game.rng import GameRng
from lorecraft.services.effects import EffectService
from lorecraft.services.meters import MeterService
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.services.movement import MovementService


def test_movement_service_moves_player_and_queues_event() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    manager = ConnectionManager()
    observed = []

    with Session(engine) as session:
        _seed_rooms(session)
        player = _seed_player(session)
        session.commit()
        bus = EventBus()
        bus.on(
            GameEvent.PLAYER_MOVED, lambda event, ctx: observed.append(event.payload)
        )
        ctx = _build_context(session, player, manager, bus)
        manager.move_player("player-1", None, "tavern")

        MovementService().move("east", ctx)
        session.commit()
        ctx.flush_events()

        persisted = session.get(Player, "player-1")

    assert ctx.messages == ["You go east."]
    assert ctx.room_messages == ["petem leaves east."]
    assert ctx.updates == {"room_id": "square"}
    assert manager.players_in_room("square") == ["player-1"]
    assert persisted.current_room_id == "square"
    assert persisted.visited_rooms == ["square"]
    assert observed == [
        {
            "player_id": "player-1",
            "from_room_id": "tavern",
            "to_room_id": "square",
            "direction": "east",
        }
    ]


def test_unlock_requires_the_right_key() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        session.add(
            Exit(
                room_id="tavern",
                direction="north",
                target_room_id="square",
                locked=True,
                key_item_id="brass_key",
            )
        )
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().unlock("north", ctx)

    assert ctx.messages == ["You don't have the right key."]


def test_unlock_persists_and_allows_future_keyless_movement() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        session.add(
            Exit(
                room_id="tavern",
                direction="north",
                target_room_id="square",
                locked=True,
                key_item_id="brass_key",
            )
        )
        session.add(Item(id="brass_key", name="Brass Key", description="A key."))
        player = _seed_player(session)
        session.commit()
        item_location = ItemLocationService(session)
        loc = Location("player", player.id)
        stack = item_location.spawn("brass_key", loc)[0]
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().unlock("north", ctx)
        session.commit()

        assert ctx.messages == ["You unlock the way north. It is now unlocked."]

        ctx.messages.clear()
        assert stack.id is not None
        item_location.destroy(stack.id, 1)
        session.commit()
        MovementService().move("north", ctx)

    assert ctx.messages == ["You go north."]


def test_lock_sets_exit_locked_when_key_carried() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        session.add(
            Exit(
                room_id="tavern",
                direction="north",
                target_room_id="square",
                locked=False,
                key_item_id="brass_key",
            )
        )
        session.add(Item(id="brass_key", name="Brass Key", description="A key."))
        player = _seed_player(session)
        session.commit()
        ItemLocationService(session).spawn("brass_key", Location("player", player.id))
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().lock("north", ctx)

    assert ctx.messages == ["You lock the way north. It is now locked."]


def test_unlock_without_direction_prompts() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().unlock(None, ctx)

    assert ctx.messages == ["Unlock which way?"]


def test_movement_service_blocks_missing_exit() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().move("north", ctx)

    assert ctx.messages == ["You can't go that way."]
    assert ctx.player.current_room_id == "tavern"


def _seed_rooms(session: Session) -> None:
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
        Room(
            id="square",
            name="Square",
            description="A busy square.",
            map_x=1,
            map_y=0,
        )
    )
    session.add(Exit(room_id="tavern", direction="east", target_room_id="square"))


def _seed_player(session: Session) -> Player:
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="tavern",
        respawn_room_id="tavern",
    )
    session.add(player)
    return player


def _build_context(
    session: Session,
    player: Player,
    manager: ConnectionManager,
    bus: EventBus,
) -> GameContext:
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
        manager=manager,
        bus=bus,
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
