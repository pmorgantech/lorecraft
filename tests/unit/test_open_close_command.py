"""Tests for standard components (durability/openable/lit/container) and the
`open`/`close` commands (Sprint 22.2)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

import lorecraft.game.standard_components  # noqa: F401 -- registration side effects
from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.engine import CommandEngine
from lorecraft.game.events import EventBus
from lorecraft.game.holders import Location
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rng import GameRng
from lorecraft.game.rules import RuleEngine
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.items import ItemInstance
from lorecraft.models.player import Player
from lorecraft.models.world import Item, Room
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.effects import EffectService
from lorecraft.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.services.meters import MeterService

ROOM_ID = "room-1"


def _build_engine_and_ctx() -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    session.add(Room(id=ROOM_ID, name="Room One", description="d", map_x=0, map_y=0))
    session.add(
        Item(
            id="chest",
            name="wooden chest",
            description="A sturdy chest.",
            takeable=False,
            capacity=50.0,
        )
    )
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=ROOM_ID,
        respawn_room_id=ROOM_ID,
    )
    session.add(player)
    session.commit()

    item_location = ItemLocationService(session)
    item_location.spawn("chest", Location("room", ROOM_ID))
    session.commit()

    room = session.get(Room, ROOM_ID)
    assert room is not None
    ctx = GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=item_location,
        ledger=LedgerService(),
        rng=GameRng(),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
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


@pytest.fixture
def built() -> Iterator[tuple[CommandEngine, GameContext, Session]]:
    cmd_engine, ctx, session = _build_engine_and_ctx()
    yield cmd_engine, ctx, session
    session.close()


def test_chest_spawns_with_container_and_openable_components(
    built: tuple[CommandEngine, GameContext, Session],
) -> None:
    _, ctx, session = built
    stacks = ctx.item_repo.items_in_room(ROOM_ID)
    assert len(stacks) == 1
    stack, _item = stacks[0]
    assert stack.instance_id is not None
    instance = session.get(ItemInstance, stack.instance_id)
    assert instance is not None
    assert instance.state["container"] == {}
    assert instance.state["openable"] == {"open": False}


def test_open_command_opens_chest(
    built: tuple[CommandEngine, GameContext, Session],
) -> None:
    cmd_engine, ctx, session = built

    cmd_engine.handle_command("open chest", ctx)

    assert ctx.messages == ["You open the wooden chest."]
    stack, _item = ctx.item_repo.items_in_room(ROOM_ID)[0]
    instance = session.get(ItemInstance, stack.instance_id)
    assert instance is not None
    assert instance.state["openable"]["open"] is True


def test_open_command_twice_reports_already_open(
    built: tuple[CommandEngine, GameContext, Session],
) -> None:
    cmd_engine, ctx, _session = built

    cmd_engine.handle_command("open chest", ctx)
    ctx.messages.clear()
    cmd_engine.handle_command("open chest", ctx)

    assert ctx.messages == ["The wooden chest is already open."]


def test_close_command_closes_open_chest(
    built: tuple[CommandEngine, GameContext, Session],
) -> None:
    cmd_engine, ctx, session = built

    cmd_engine.handle_command("open chest", ctx)
    ctx.messages.clear()
    cmd_engine.handle_command("close chest", ctx)

    assert ctx.messages == ["You close the wooden chest."]
    stack, _item = ctx.item_repo.items_in_room(ROOM_ID)[0]
    instance = session.get(ItemInstance, stack.instance_id)
    assert instance is not None
    assert instance.state["openable"]["open"] is False


def test_close_command_already_closed(
    built: tuple[CommandEngine, GameContext, Session],
) -> None:
    cmd_engine, ctx, _session = built

    cmd_engine.handle_command("close chest", ctx)

    assert ctx.messages == ["The wooden chest is already closed."]


def test_open_non_openable_item_reports_cannot(
    built: tuple[CommandEngine, GameContext, Session],
) -> None:
    cmd_engine, ctx, session = built
    session.add(Item(id="rock", name="rock", description="A rock."))
    session.commit()
    ItemLocationService(session).spawn("rock", Location("room", ROOM_ID))
    session.commit()

    cmd_engine.handle_command("open rock", ctx)

    assert ctx.messages == ["You can't open that."]
