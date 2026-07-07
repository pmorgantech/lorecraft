"""Sprint 52.2/52.3: channel-aware chat outbox + scope-routed broadcast."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.broadcast import broadcast_command_effects
from lorecraft.engine.game.channels import Channel, ChatScope
from lorecraft.engine.game.channels import get_registry as channel_registry
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.types import JsonObject


class _RecordingSocket:
    def __init__(self) -> None:
        self.sent: list[JsonObject] = []

    async def accept(self) -> None:  # pragma: no cover - protocol completeness
        pass

    async def send_json(self, data: JsonObject) -> None:
        self.sent.append(data)

    def chats(self) -> list[tuple[str, str]]:
        return [
            (str(m.get("channel")), str(m.get("content")))
            for m in self.sent
            if m.get("message_type") == "chat"
        ]


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        yield session


def _player(session: Session, pid: str, room: str, **kw: object) -> Player:
    player = Player(
        id=pid, username=pid.title(), current_room_id=room, respawn_room_id=room, **kw
    )
    session.add(player)
    session.add(PlayerStats(player_id=pid))
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


def _wire(manager: ConnectionManager, pid: str, room: str) -> _RecordingSocket:
    socket = _RecordingSocket()
    manager._connections[pid] = socket  # type: ignore[assignment]
    manager.move_player(pid, None, room)
    return socket


def _setup(session: Session) -> tuple[ConnectionManager, dict[str, _RecordingSocket]]:
    session.add(Room(id="tavern", name="Tavern", description="d", map_x=0, map_y=0))
    session.add(Room(id="road", name="Road", description="d", map_x=1, map_y=0))
    manager = ConnectionManager()
    sockets = {
        "actor": _wire(manager, "actor", "tavern"),
        "neighbor": _wire(manager, "neighbor", "tavern"),
        "traveler": _wire(manager, "traveler", "road"),
    }
    _player(session, "actor", "tavern")
    _player(session, "neighbor", "tavern")
    _player(session, "traveler", "road")
    session.commit()
    return manager, sockets


def _run(ctx: GameContext, manager: ConnectionManager) -> None:
    asyncio.run(broadcast_command_effects(manager, ctx, pre_room_id="tavern"))


class TestScopeRouting:
    def test_p2room_reaches_room_only_and_never_the_actor(
        self, session: Session
    ) -> None:
        manager, sockets = _setup(session)
        ctx = _ctx(session, session.get(Player, "actor"), manager)  # type: ignore[arg-type]
        ctx.tell_room_chat('Actor says: "hi"')
        _run(ctx, manager)

        assert sockets["neighbor"].chats() == [("say", 'Actor says: "hi"')]
        assert sockets["traveler"].chats() == []
        assert sockets["actor"].chats() == []

    def test_p2p_reaches_exactly_the_target(self, session: Session) -> None:
        manager, sockets = _setup(session)
        ctx = _ctx(session, session.get(Player, "actor"), manager)  # type: ignore[arg-type]
        ctx.chat_out("tell", 'Actor tells you: "psst"', target_player_id="traveler")
        _run(ctx, manager)

        assert sockets["traveler"].chats() == [("tell", 'Actor tells you: "psst"')]
        assert sockets["neighbor"].chats() == []
        assert sockets["actor"].chats() == []

    def test_p2all_reaches_every_room_except_the_actor(self, session: Session) -> None:
        channel_registry().register(
            Channel(id="newbie", scope=ChatScope.P2ALL, tag="Newbie", muteable=True)
        )
        manager, sockets = _setup(session)
        ctx = _ctx(session, session.get(Player, "actor"), manager)  # type: ignore[arg-type]
        ctx.chat_out("newbie", '(Newbie) Actor: "hello world"')
        _run(ctx, manager)

        assert sockets["neighbor"].chats() == [
            ("newbie", '(Newbie) Actor: "hello world"')
        ]
        assert sockets["traveler"].chats() == [
            ("newbie", '(Newbie) Actor: "hello world"')
        ]
        assert sockets["actor"].chats() == []


class TestSubscriptionDrop:
    def test_unsubscribed_recipient_is_dropped(self, session: Session) -> None:
        channel_registry().register(
            Channel(id="newbie", scope=ChatScope.P2ALL, tag="Newbie", muteable=True)
        )
        manager, sockets = _setup(session)
        traveler = session.get(Player, "traveler")
        assert traveler is not None
        traveler.preferences = {"channel_subscriptions": {"newbie": False}}
        session.add(traveler)
        session.commit()

        ctx = _ctx(session, session.get(Player, "actor"), manager)  # type: ignore[arg-type]
        ctx.chat_out("newbie", '(Newbie) Actor: "hi"')
        _run(ctx, manager)

        assert sockets["neighbor"].chats() == [("newbie", '(Newbie) Actor: "hi"')]
        assert sockets["traveler"].chats() == []

    def test_opt_in_channel_delivers_only_to_subscribers(
        self, session: Session
    ) -> None:
        channel_registry().register(
            Channel(
                id="auction-test",
                scope=ChatScope.P2ALL,
                tag="Auction",
                muteable=True,
                default_subscribed=False,
            )
        )
        manager, sockets = _setup(session)
        neighbor = session.get(Player, "neighbor")
        assert neighbor is not None
        neighbor.preferences = {"channel_subscriptions": {"auction-test": True}}
        session.add(neighbor)
        session.commit()

        ctx = _ctx(session, session.get(Player, "actor"), manager)  # type: ignore[arg-type]
        ctx.chat_out("auction-test", "(Auction) Actor: selling boots")
        _run(ctx, manager)

        assert sockets["neighbor"].chats() == [
            ("auction-test", "(Auction) Actor: selling boots")
        ]
        assert sockets["traveler"].chats() == []


class TestEchoes:
    def test_echoes_never_broadcast(self, session: Session) -> None:
        manager, sockets = _setup(session)
        ctx = _ctx(session, session.get(Player, "actor"), manager)  # type: ignore[arg-type]
        ctx.say_chat('You say: "hi"')
        _run(ctx, manager)

        assert [m.text for m in ctx.chat_echoes] == ['You say: "hi"']
        assert all(s.chats() == [] for s in sockets.values())

    def test_unknown_channel_falls_back_to_room_scope(self, session: Session) -> None:
        manager, sockets = _setup(session)
        ctx = _ctx(session, session.get(Player, "actor"), manager)  # type: ignore[arg-type]
        ctx.chat_out("no-such-channel", "hello?")
        _run(ctx, manager)

        # Fallback is P2ROOM — never accidentally global.
        assert sockets["neighbor"].chats() == [("no-such-channel", "hello?")]
        assert sockets["traveler"].chats() == []
