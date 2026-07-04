"""Tests for the `give` command and InventoryService.give_item()."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.engine import CommandEngine
from lorecraft.game.events import EventBus, GameEvent
from lorecraft.game.holders import Location
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rules import RuleEngine
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player
from lorecraft.models.world import NPC, Room
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.item_location import ItemLocationService
from lorecraft.game.rng import GameRng
from lorecraft.services.effects import EffectService
from lorecraft.services.meters import MeterService
from tests.fixtures.disambig_fixtures import DISAMBIG_ROOM_ID, seed_disambig_gallery


def _build_engine_and_ctx(
    inventory: list[str], *, with_npc: bool = True
) -> tuple[CommandEngine, GameContext]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    seed_disambig_gallery(session, link=None)
    if with_npc:
        session.add(
            NPC(
                id="mira",
                name="Mira",
                description="The innkeeper.",
                current_room_id=DISAMBIG_ROOM_ID,
                home_room_id=DISAMBIG_ROOM_ID,
                dialogue_tree_id="",
            )
        )
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=DISAMBIG_ROOM_ID,
        respawn_room_id=DISAMBIG_ROOM_ID,
    )
    session.add(player)
    session.commit()
    item_location = ItemLocationService(session)
    for item_id in inventory:
        item_location.spawn(item_id, Location("player", player.id))
    session.commit()
    room = session.get(Room, DISAMBIG_ROOM_ID)
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
    return CommandEngine(registry, RuleEngine()), ctx


def _carried_item_ids(ctx: GameContext) -> list[str]:
    ids: list[str] = []
    for stack in ctx.stack_repo.stacks_for_owner("player", ctx.player.id):
        ids.extend([stack.item_id] * stack.quantity)
    return ids


def test_give_item_to_npc_removes_it_from_inventory() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["red_rose"])

    cmd_engine.handle_command("give red rose to mira", ctx)

    assert ctx.messages == ["You give the Red Rose to Mira."]
    assert _carried_item_ids(ctx) == []


def test_give_without_recipient_prompts() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["red_rose"])

    cmd_engine.handle_command("give red rose", ctx)

    assert ctx.messages == ["Give it to whom?"]
    assert _carried_item_ids(ctx) == ["red_rose"]


def test_give_unknown_recipient_says_not_here() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["red_rose"], with_npc=False)

    cmd_engine.handle_command("give red rose to mira", ctx)

    assert ctx.messages == ["There is no mira here."]
    assert _carried_item_ids(ctx) == ["red_rose"]


def test_give_item_not_carried_says_you_dont_have_it() -> None:
    cmd_engine, ctx = _build_engine_and_ctx([])

    cmd_engine.handle_command("give red rose to mira", ctx)

    assert ctx.messages == ["You don't have that."]


def test_give_ambiguous_item_prompts_numbered_choices() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["iron_key", "red_key"])

    cmd_engine.handle_command("give key to mira", ctx)

    assert ctx.messages[0].startswith("Which do you mean?")
    assert ctx.updates["disambig_pending"]["verb"] == "give"


def test_give_emits_item_given_event() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["red_rose"])
    seen = []
    ctx.bus.on(
        GameEvent.ITEM_GIVEN,
        lambda event, _ctx: seen.append(
            (event.payload["item_id"], event.payload["npc_id"])
        ),
    )

    cmd_engine.handle_command("give red rose to mira", ctx)

    assert seen == [("red_rose", "mira")]
