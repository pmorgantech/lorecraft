from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext, build_game_context
from lorecraft.engine.game.events import EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room, WorldClock
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService


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
            session=session,
            player_repo=player_repo,
            room_repo=room_repo,
            item_repo=ItemRepo(session),
            stack_repo=StackRepo(session),
            item_location=ItemLocationService(session),
            ledger=LedgerService(),
            npc_repo=NpcRepo(session),
            manager=manager,
            bus=bus,
            audit=None,
            transaction=TransactionContext.create(
                actor_id="player-1", correlation_id="session-1"
            ),
            session_id="session-1",
            rng=GameRng(),
            meters=MeterService(engine, GameRng()),
            effects=EffectService(engine, GameRng()),
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
            rng=GameRng(),
            meters=MeterService(engine, GameRng()),
            effects=EffectService(engine, GameRng()),
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


def test_build_game_context_clock_defaults_to_none() -> None:
    """Factory passes `clock` straight through — no synthesized fallback.

    Real callers pass `room_repo.world_clock()`, which is `None` if the
    world has no seeded clock row; fabricating a fake one here would be
    silently wrong data, not a safe default.
    """
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
            rng=GameRng(),
            meters=MeterService(engine, GameRng()),
            effects=EffectService(engine, GameRng()),
        )

        assert ctx.clock is None


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
            rng=GameRng(),
            meters=MeterService(engine, GameRng()),
            effects=EffectService(engine, GameRng()),
            clock=custom_clock,
        )

        assert ctx.clock == custom_clock
        assert ctx.clock.current_hour == 10


def test_build_game_context_with_audit_session() -> None:
    """Factory creates AuditRepo when an audit_session is given.

    Production always uses a separate DB/engine for audit events, so this
    takes its own `Session` rather than reusing the game-state one.
    """
    engine = create_engine("sqlite://")
    audit_engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=audit_engine)

    with Session(engine) as session, Session(audit_engine) as audit_session:
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
            rng=GameRng(),
            meters=MeterService(engine, GameRng()),
            effects=EffectService(engine, GameRng()),
            audit_session=audit_session,
        )

        assert ctx.audit is not None


def test_build_game_context_without_audit_session_leaves_audit_none() -> None:
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
            rng=GameRng(),
            meters=MeterService(engine, GameRng()),
            effects=EffectService(engine, GameRng()),
        )

        assert ctx.audit is None


def test_build_game_context_wires_commit_and_rollback_callables() -> None:
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
        calls: list[str] = []

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
            rng=GameRng(),
            meters=MeterService(engine, GameRng()),
            effects=EffectService(engine, GameRng()),
            commit_state=lambda: calls.append("commit_state"),
            commit_audit=lambda: calls.append("commit_audit"),
            rollback_state=lambda: calls.append("rollback_state"),
        )

        ctx.commit_state_changes()
        ctx.commit_audit_events()
        ctx.rollback_state_changes()

        assert calls == ["commit_state", "commit_audit", "rollback_state"]


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
            rng=GameRng(),
            meters=MeterService(engine, GameRng()),
            effects=EffectService(engine, GameRng()),
        )

        assert isinstance(ctx, GameContext)
