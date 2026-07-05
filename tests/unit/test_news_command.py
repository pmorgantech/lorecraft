"""Tests for the `news` command."""

from __future__ import annotations

import time

from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.models.news import NewsItem
from lorecraft.models.player import Player
from lorecraft.models.world import Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.repos.news_repo import NewsRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo


def _build_engine_and_ctx() -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    room = Room(
        id="square", name="Square", description="A busy square.", map_x=0, map_y=0
    )
    session.add(room)
    player = Player(
        id="player-1",
        username="tester",
        current_room_id="square",
        respawn_room_id="square",
    )
    session.add(player)
    session.commit()
    ctx = GameContext(
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
        news_repo=NewsRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
    registry = CommandRegistry()
    register_all_commands(registry)
    return CommandEngine(registry, RuleEngine()), ctx, session


def test_news_command_with_no_announcements() -> None:
    cmd_engine, ctx, _session = _build_engine_and_ctx()

    cmd_engine.handle_command("news", ctx)

    assert ctx.messages == ["No news right now."]


def test_slash_news_alias_behaves_identically() -> None:
    cmd_engine, ctx, _session = _build_engine_and_ctx()

    cmd_engine.handle_command("/news", ctx)

    assert ctx.messages == ["No news right now."]


def test_news_command_lists_active_announcement() -> None:
    cmd_engine, ctx, session = _build_engine_and_ctx()
    now = time.time()
    session.add(
        NewsItem(
            id="news-001",
            type="patch",
            title="Welcome to Ashmoore",
            body="A new quest line begins.",
            published_at=now - 10,
            expires_at=None,
        )
    )
    session.commit()

    cmd_engine.handle_command("news", ctx)

    assert len(ctx.messages) == 1
    assert "Welcome to Ashmoore" in ctx.messages[0]
    assert "A new quest line begins." in ctx.messages[0]


def test_news_command_hides_expired_announcement() -> None:
    cmd_engine, ctx, session = _build_engine_and_ctx()
    now = time.time()
    session.add(
        NewsItem(
            id="news-001",
            title="Old maintenance notice",
            published_at=now - 1000,
            expires_at=now - 10,
        )
    )
    session.commit()

    cmd_engine.handle_command("news", ctx)

    assert ctx.messages == ["No news right now."]
