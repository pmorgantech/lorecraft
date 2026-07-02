from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext, build_game_context
from lorecraft.game.events import EventBus, GameEvent
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player
from lorecraft.models.world import Room, WorldClock
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo


def test_context_collects_messages_updates_and_emits_events() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    bus = EventBus()
    observed = []
    bus.on(
        GameEvent.PLAYER_MOVED,
        lambda event, ctx: observed.append((event.payload, ctx.session_id)),
    )
    manager = ConnectionManager()

    with Session(engine) as session:
        player_repo = PlayerRepo(session)
        room_repo = RoomRepo(session)
        player = Player(
            id="player-1",
            username="petem",
            current_room_id="tavern",
            respawn_room_id="tavern",
        )
        room = Room(
            id="tavern",
            name="Tavern",
            description="A warm room.",
            map_x=0,
            map_y=0,
        )
        ctx = GameContext(
            player=player,
            room=room,
            clock=None,
            player_repo=player_repo,
            room_repo=room_repo,
            item_repo=ItemRepo(session),
            npc_repo=NpcRepo(session),
            manager=manager,
            bus=bus,
            audit=None,
            transaction=TransactionContext.create(
                actor_id="player-1", correlation_id="session-1"
            ),
            session_id="session-1",
        )

        ctx.say("You move north.")
        ctx.tell_room("Player leaves north.")
        ctx.push_update("room", "square")
        ctx.emit(GameEvent.PLAYER_MOVED, room_id="square")

        assert ctx.messages == ["You move north."]
        assert ctx.room_messages == ["Player leaves north."]
        assert ctx.updates == {"room": "square"}
        assert observed == [({"room_id": "square"}, "session-1")]


def test_build_game_context_wires_all_repos() -> None:
    """Factory returns fully-wired GameContext with all repos."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = Player(
            id="test-1",
            username="test",
            current_room_id="room-1",
            respawn_room_id="room-1",
        )
        room = Room(id="room-1", name="Test Room", map_x=0, map_y=0)
        bus = EventBus()
        manager = ConnectionManager()
        transaction = TransactionContext.create(
            actor_id="test-1", correlation_id="test"
        )

        ctx = build_game_context(
            session,
            player,
            room,
            bus=bus,
            manager=manager,
            transaction=transaction,
            session_id="session-1",
        )

        assert ctx.player == player
        assert ctx.room == room
        assert ctx.bus == bus
        assert ctx.manager == manager
        assert ctx.transaction == transaction
        assert ctx.session_id == "session-1"
        assert ctx.player_repo is not None
        assert ctx.room_repo is not None
        assert ctx.item_repo is not None
        assert ctx.npc_repo is not None
        assert ctx.quest_repo is not None
        assert ctx.dialogue_repo is not None


def test_build_game_context_default_clock() -> None:
    """Factory creates default WorldClock if not provided."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = Player(
            id="test-1",
            username="test",
            current_room_id="room-1",
            respawn_room_id="room-1",
        )
        room = Room(id="room-1", name="Test Room", map_x=0, map_y=0)

        ctx = build_game_context(
            session,
            player,
            room,
            bus=EventBus(),
            manager=ConnectionManager(),
            transaction=TransactionContext.create(
                actor_id="test-1", correlation_id="test"
            ),
            session_id="session-1",
        )

        assert ctx.clock is not None
        assert isinstance(ctx.clock, WorldClock)


def test_build_game_context_custom_clock() -> None:
    """Factory uses provided clock."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = Player(
            id="test-1",
            username="test",
            current_room_id="room-1",
            respawn_room_id="room-1",
        )
        room = Room(id="room-1", name="Test Room", map_x=0, map_y=0)
        custom_clock = WorldClock(
            game_epoch=1000.0,
            real_epoch=2000.0,
            current_hour=10,
        )

        ctx = build_game_context(
            session,
            player,
            room,
            bus=EventBus(),
            manager=ConnectionManager(),
            transaction=TransactionContext.create(
                actor_id="test-1", correlation_id="test"
            ),
            session_id="session-1",
            clock=custom_clock,
        )

        assert ctx.clock == custom_clock
        assert ctx.clock.current_hour == 10


def test_build_game_context_with_audit_repo() -> None:
    """Factory creates AuditRepo when create_audit_repo is True."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = Player(
            id="test-1",
            username="test",
            current_room_id="room-1",
            respawn_room_id="room-1",
        )
        room = Room(id="room-1", name="Test Room", map_x=0, map_y=0)

        ctx = build_game_context(
            session,
            player,
            room,
            bus=EventBus(),
            manager=ConnectionManager(),
            transaction=TransactionContext.create(
                actor_id="test-1", correlation_id="test"
            ),
            session_id="session-1",
            create_audit_repo=True,
        )

        assert ctx.audit is not None


def test_build_game_context_is_type_game_context() -> None:
    """Factory returns GameContext instance."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        player = Player(
            id="test-1",
            username="test",
            current_room_id="room-1",
            respawn_room_id="room-1",
        )
        room = Room(id="room-1", name="Test Room", map_x=0, map_y=0)

        ctx = build_game_context(
            session,
            player,
            room,
            bus=EventBus(),
            manager=ConnectionManager(),
            transaction=TransactionContext.create(
                actor_id="test-1", correlation_id="test"
            ),
            session_id="session-1",
        )

        assert isinstance(ctx, GameContext)
