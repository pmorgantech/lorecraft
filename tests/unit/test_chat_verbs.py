"""Sprint 52.4: the `tell` verb + verb-per-channel topic speaking."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.engine.game.channels import ChatScope
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room
from tests.unit.test_chat_broadcast import _ctx, _player, _RecordingSocket


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        yield session


@pytest.fixture
def registry() -> CommandRegistry:
    registry = CommandRegistry()
    register_all_commands(registry)
    return registry


def _seed(session: Session) -> tuple[Player, Player]:
    session.add(Room(id="tavern", name="Tavern", description="d", map_x=0, map_y=0))
    speaker = _player(session, "speaker", "tavern")
    listener = _player(session, "listener", "tavern")
    session.commit()
    return speaker, listener


class TestTell:
    def test_tell_online_player(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        speaker, listener = _seed(session)
        manager = ConnectionManager()
        manager._connections["listener"] = object()  # type: ignore[assignment]
        ctx = _ctx(session, speaker, manager)

        registry.get("tell").handler("Listener meet me at the inn", ctx)

        assert [m.text for m in ctx.chat_echoes] == [
            'You tell Listener: "meet me at the inn"'
        ]
        assert listener.flags["_last_tell_from"] == speaker.id
        assert len(ctx.chat_outbox) == 1
        out = ctx.chat_outbox[0]
        assert out.text == 'Speaker tells you: "meet me at the inn"'
        assert out.channel == "tell"
        assert out.scope is ChatScope.P2P
        assert out.target_player_id == "listener"

    def test_tell_offline_player_rejected(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        speaker, _listener = _seed(session)
        ctx = _ctx(session, speaker, ConnectionManager())  # nobody connected

        registry.get("tell").handler("Listener hello", ctx)

        assert ctx.messages == ["Listener isn't online right now."]
        assert ctx.chat_outbox == []

    def test_tell_unknown_and_self_and_empty(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        speaker, _listener = _seed(session)
        manager = ConnectionManager()

        ctx = _ctx(session, speaker, manager)
        registry.get("tell").handler(None, ctx)
        assert ctx.messages == ["Tell whom what?"]

        ctx = _ctx(session, speaker, manager)
        registry.get("tell").handler("Listener", ctx)
        assert ctx.messages == ["Tell them what?"]

        ctx = _ctx(session, speaker, manager)
        registry.get("tell").handler("Nobody hi", ctx)
        assert ctx.messages == ["There's no one called 'Nobody'."]

        ctx = _ctx(session, speaker, manager)
        registry.get("tell").handler("Speaker hi", ctx)
        assert ctx.messages == ["You mutter to yourself."]
        assert ctx.chat_outbox == []


class TestReply:
    def test_reply_uses_last_tell_sender(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        speaker, listener = _seed(session)
        speaker.flags = {"_last_tell_from": listener.id}
        session.commit()
        manager = ConnectionManager()
        manager._connections[listener.id] = object()  # type: ignore[assignment]
        ctx = _ctx(session, speaker, manager)

        registry.get("reply").handler("on my way", ctx)

        assert [m.text for m in ctx.chat_echoes] == ['You tell Listener: "on my way"']
        assert ctx.chat_outbox[0].target_player_id == listener.id
        assert listener.flags["_last_tell_from"] == speaker.id

    def test_reply_without_sender_warns(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        speaker, _listener = _seed(session)
        ctx = _ctx(session, speaker, ConnectionManager())

        registry.get("reply").handler("hello?", ctx)

        assert ctx.messages == ["No one has told you anything to reply to."]


class TestWho:
    def test_who_lists_online_players_globally(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        speaker, listener = _seed(session)
        session.add(Room(id="market", name="Market", description="d", map_x=1, map_y=0))
        distant = _player(session, "distant", "market")
        offline = _player(session, "offline", "market")
        session.commit()
        manager = ConnectionManager()
        manager._connections[speaker.id] = object()  # type: ignore[assignment]
        manager._connections[listener.id] = object()  # type: ignore[assignment]
        manager._connections[distant.id] = object()  # type: ignore[assignment]
        ctx = _ctx(session, speaker, manager)

        registry.get("who").handler(None, ctx)

        assert ctx.messages == ["Online players: Distant, Listener, Speaker"]
        assert offline.username not in ctx.messages[0]

    def test_who_reports_empty_roster(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        speaker, _listener = _seed(session)
        ctx = _ctx(session, speaker, ConnectionManager())

        registry.get("who").handler(None, ctx)

        assert ctx.messages == ["No players are online."]


class TestShout:
    def test_shout_reaches_connected_players_in_same_zone(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        session.add(
            Room(
                id="tavern",
                name="Tavern",
                description="d",
                map_x=0,
                map_y=0,
                zone="town",
            )
        )
        session.add(
            Room(
                id="market",
                name="Market",
                description="d",
                map_x=1,
                map_y=0,
                zone="town",
            )
        )
        session.add(
            Room(
                id="forest",
                name="Forest",
                description="d",
                map_x=9,
                map_y=9,
                zone="wilds",
            )
        )
        speaker = _player(session, "speaker", "tavern")
        near = _player(session, "near", "market")
        far = _player(session, "far", "forest")
        session.commit()
        manager = ConnectionManager()
        near_socket = _RecordingSocket()
        far_socket = _RecordingSocket()
        manager._connections[near.id] = near_socket  # type: ignore[assignment]
        manager._connections[far.id] = far_socket  # type: ignore[assignment]
        ctx = _ctx(session, speaker, manager)

        registry.get("shout").handler("anyone there?", ctx)
        asyncio.run(_drain_deliveries(ctx))

        assert [m.text for m in ctx.chat_echoes] == ['You shout: "anyone there?"']
        assert near_socket.chats() == [("shout", 'Speaker shouts: "anyone there?"')]
        assert far_socket.chats() == []


async def _drain_deliveries(ctx) -> None:
    for delivery in ctx.pending_deliveries:
        await delivery()


class TestTopicVerbs:
    def test_newbie_verb_speaks_on_the_channel(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        speaker, _listener = _seed(session)
        ctx = _ctx(session, speaker, ConnectionManager())

        command = registry.get("newbie")
        assert command is not None, "newbie channel verb should auto-register"
        command.handler("how do I open the vault?", ctx)

        assert [m.text for m in ctx.chat_echoes] == [
            '(Newbie) You: "how do I open the vault?"'
        ]
        out = ctx.chat_outbox[0]
        assert out.text == '(Newbie) Speaker: "how do I open the vault?"'
        assert out.channel == "newbie"
        assert out.scope is ChatScope.P2ALL

    def test_empty_topic_message_stays_narrative(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        speaker, _listener = _seed(session)
        ctx = _ctx(session, speaker, ConnectionManager())

        registry.get("newbie").handler(None, ctx)

        assert ctx.messages == ["Say what on the Newbie channel?"]
        assert ctx.chat_echoes == []
        assert ctx.chat_outbox == []
