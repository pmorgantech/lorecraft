"""Follow feature (Sprint 47): social-movement cascade and gate-break."""

from __future__ import annotations

import anyio
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Exit, Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.follow.service import FollowService
from lorecraft.features.movement.service import MovementService

ROOM_A = "square"
ROOM_B = "market"


class _FakeSocket:
    async def accept(self) -> None:  # pragma: no cover - protocol completeness
        pass

    async def send_json(self, data: object) -> None:  # pragma: no cover
        pass


class _RecordingSocket:
    """A socket that records every pushed message, for disconnect-notice asserts."""

    def __init__(self) -> None:
        self.sent: list[object] = []

    async def accept(self) -> None:  # pragma: no cover - protocol completeness
        pass

    async def send_json(self, data: object) -> None:
        self.sent.append(data)


def _seed(session: Session, *, locked_east: bool = False) -> None:
    session.add(Room(id=ROOM_A, name="Square", description="d", map_x=0, map_y=0))
    session.add(Room(id=ROOM_B, name="Market", description="d", map_x=1, map_y=0))
    session.add(
        Exit(
            room_id=ROOM_A,
            direction="east",
            target_room_id=ROOM_B,
            locked=locked_east,
        )
    )
    session.commit()


def _add_player(session: Session, pid: str, name: str, room_id: str) -> Player:
    player = Player(
        id=pid, username=name, current_room_id=room_id, respawn_room_id=room_id
    )
    session.add(player)
    session.add(PlayerStats(player_id=pid))
    session.commit()
    return player


def _ctx(session: Session, player: Player, manager: ConnectionManager) -> GameContext:
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
        rng=GameRng(seed=1),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=manager,
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id=player.id, correlation_id="s1"),
        session_id="s1",
    )


def _connect(manager: ConnectionManager, pid: str, room_id: str) -> None:
    manager._connections[pid] = _FakeSocket()  # type: ignore[assignment]
    manager.move_player(pid, None, room_id)


def test_follower_moves_with_target() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        _seed(session)
        target = _add_player(session, "p-target", "Aldric", ROOM_A)
        follower = _add_player(session, "p-follow", "Bryn", ROOM_A)
        manager = ConnectionManager()
        _connect(manager, target.id, ROOM_A)
        _connect(manager, follower.id, ROOM_A)

        follow = FollowService(MovementService())
        bus = EventBus()
        follow.register(bus)

        # Bryn follows Aldric.
        follow.follow("Aldric", _ctx(session, follower, manager))
        assert follow.target_of("p-follow") == "p-target"

        # Aldric walks east; the flushed PLAYER_MOVED drives the follow.
        ctx = _ctx(session, target, manager)
        ctx.bus = bus
        MovementService().move("east", ctx)
        ctx.flush_events()

        # In-memory state after the cascade (the real command loop commits
        # after flush; here we assert the mutation the handler made).
        assert target.current_room_id == ROOM_B
        assert follower.current_room_id == ROOM_B
        # The follower's socket got a follow feed + panel refresh queued.
        assert len(ctx.pending_deliveries) >= 2


def test_follow_chain_cascades() -> None:
    """A follows B follows C: when C moves, the whole chain walks (each
    auto-move emits its own PLAYER_MOVED, so the cascade is recursive)."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        _seed(session)
        c = _add_player(session, "c", "Cyra", ROOM_A)  # leader
        b = _add_player(session, "b", "Bram", ROOM_A)
        a = _add_player(session, "a", "Aria", ROOM_A)
        manager = ConnectionManager()
        for pid in ("c", "b", "a"):
            _connect(manager, pid, ROOM_A)

        follow = FollowService(MovementService())
        bus = EventBus()
        follow.register(bus)
        follow.follow("Cyra", _ctx(session, b, manager))  # Bram -> Cyra
        follow.follow("Bram", _ctx(session, a, manager))  # Aria -> Bram

        ctx = _ctx(session, c, manager)
        ctx.bus = bus
        MovementService().move("east", ctx)
        ctx.flush_events()

        assert c.current_room_id == ROOM_B
        assert b.current_room_id == ROOM_B
        assert a.current_room_id == ROOM_B


def test_follow_command_rejects_self_and_absent_targets() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        _seed(session)
        player = _add_player(session, "p1", "Solo", ROOM_A)
        manager = ConnectionManager()
        _connect(manager, player.id, ROOM_A)
        follow = FollowService()

        ctx = _ctx(session, player, manager)
        follow.follow("Solo", ctx)
        assert ctx.messages[-1] == "You can't follow yourself."

        ctx2 = _ctx(session, player, manager)
        follow.follow("Ghost", ctx2)
        assert "no one here called Ghost" in ctx2.messages[-1]


def test_follow_rejects_cycles() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        _seed(session)
        a = _add_player(session, "a", "Ada", ROOM_A)
        b = _add_player(session, "b", "Ben", ROOM_A)
        manager = ConnectionManager()
        _connect(manager, a.id, ROOM_A)
        _connect(manager, b.id, ROOM_A)
        follow = FollowService()

        # Ada follows Ben.
        follow.follow("Ben", _ctx(session, a, manager))
        assert follow.target_of("a") == "b"

        # Ben trying to follow Ada would close a cycle — rejected.
        ctx = _ctx(session, b, manager)
        follow.follow("Ada", ctx)
        assert follow.target_of("b") is None
        assert "already following you" in ctx.messages[-1]


def test_gate_failure_breaks_the_follow() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        _seed(session, locked_east=True)  # follower can't pass the locked exit
        target = _add_player(session, "t", "Lead", ROOM_A)
        follower = _add_player(session, "f", "Tail", ROOM_A)
        manager = ConnectionManager()
        _connect(manager, target.id, ROOM_A)
        _connect(manager, follower.id, ROOM_A)

        follow = FollowService(MovementService())
        bus = EventBus()
        follow.register(bus)
        follow._following["f"] = "t"

        # Simulate the target having already stepped east through the locked
        # exit (they carry the key / aren't gated here) and fire their
        # PLAYER_MOVED — the follower, lacking passage, must fail the gate.
        target.current_room_id = ROOM_B
        manager.move_player(target.id, ROOM_A, ROOM_B)
        session.commit()

        ctx = _ctx(session, target, manager)
        ctx.bus = bus
        bus.emit(
            Event(
                GameEvent.PLAYER_MOVED,
                {
                    "player_id": "t",
                    "from_room_id": ROOM_A,
                    "to_room_id": ROOM_B,
                    "direction": "east",
                },
            ),
            ctx,
        )

        # The locked exit stopped the follower; the follow was broken.
        assert follower.current_room_id == ROOM_A
        assert follow.target_of("f") is None
        # Both sides were notified (follower push + target push queued).
        assert ctx.pending_deliveries


def test_disconnect_of_target_terminates_and_notifies_followers() -> None:
    """When the followed player disconnects, each follower's follow is cleared
    and the still-connected follower is told, so it doesn't silently resume
    when the target returns."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        _seed(session)
        target = _add_player(session, "p-target", "Aldric", ROOM_A)
        follower = _add_player(session, "p-follow", "Bryn", ROOM_A)
        manager = ConnectionManager()
        _connect(manager, target.id, ROOM_A)
        follower_socket = _RecordingSocket()
        manager._connections[follower.id] = follower_socket  # type: ignore[assignment]
        manager.move_player(follower.id, None, ROOM_A)

        follow = FollowService(MovementService())
        follow._following["p-follow"] = "p-target"

        anyio.run(follow.break_on_disconnect, manager, PlayerRepo(session), target.id)

        # Follow graph cleared both ways.
        assert follow.target_of("p-follow") is None
        assert follow.followers_of("p-target") == []
        # The follower was told, and its players-online panel nudged.
        feed = [m for m in follower_socket.sent if m.get("type") == "feed_append"]
        assert feed and "Aldric" in feed[0]["content"]
        assert any(m.get("type") == "state_change" for m in follower_socket.sent)


def test_disconnect_of_follower_terminates_and_notifies_target() -> None:
    """When a follower disconnects, their follow is cleared and the target
    (still connected) is told they lost a follower."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        _seed(session)
        target = _add_player(session, "p-target", "Aldric", ROOM_A)
        follower = _add_player(session, "p-follow", "Bryn", ROOM_A)
        manager = ConnectionManager()
        target_socket = _RecordingSocket()
        manager._connections[target.id] = target_socket  # type: ignore[assignment]
        manager.move_player(target.id, None, ROOM_A)
        _connect(manager, follower.id, ROOM_A)

        follow = FollowService(MovementService())
        follow._following["p-follow"] = "p-target"

        anyio.run(follow.break_on_disconnect, manager, PlayerRepo(session), follower.id)

        assert follow.target_of("p-follow") is None
        feed = [m for m in target_socket.sent if m.get("type") == "feed_append"]
        assert feed and "Bryn" in feed[0]["content"]
