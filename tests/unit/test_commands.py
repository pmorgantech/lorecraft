from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.events import EventBus
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player
from lorecraft.models.world import Room
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo


def test_register_all_commands_adds_meta_and_movement_commands() -> None:
    registry = CommandRegistry()

    register_all_commands(registry)

    assert registry.get("help") is not None
    assert registry.get("quit") is not None
    assert registry.get("save") is not None
    assert registry.get("load") is not None
    assert registry.get("go") is not None
    assert registry.get("north") is registry.get("go")
    assert registry.get("look") is not None
    assert registry.get("take") is not None
    assert registry.get("drop") is not None
    assert registry.get("examine") is not None
    assert registry.get("inventory") is not None


def test_meta_commands_write_context_messages_and_updates() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    registry = CommandRegistry()
    register_all_commands(registry)

    with Session(engine) as session:
        ctx = _build_context(session)

        registry.get("help").handler(None, ctx)
        registry.get("quit").handler(None, ctx)

    assert ctx.messages[0].startswith("Available commands:")
    assert "  help — show this list" in ctx.messages[0]
    assert "  go <direction>" in ctx.messages[0]
    assert ctx.messages[1] == "Goodbye."
    assert ctx.updates == {"disconnect": True}
    # Dialogue-reply commands are hidden until a conversation is active.
    assert "choice <number>" not in ctx.messages[0]
    assert "bye — end" not in ctx.messages[0]


def test_help_shows_dialogue_commands_and_hides_world_commands_in_conversation() -> (
    None
):
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    registry = CommandRegistry()
    register_all_commands(registry)

    with Session(engine) as session:
        player = Player(
            id="player-1",
            username="petem",
            current_room_id="tavern",
            respawn_room_id="tavern",
            flags={"_dialogue_npc_id": "mira"},
        )
        ctx = _build_context(session, player=player)

        registry.get("help").handler(None, ctx)

    assert ctx.messages[0].startswith("You are in conversation.")
    assert "choice <number>" in ctx.messages[0]
    assert "bye — end" in ctx.messages[0]
    assert "help — show this list" in ctx.messages[0]
    assert "go <direction>" not in ctx.messages[0]
    assert "take <item>" not in ctx.messages[0]


def test_help_hides_out_of_combat_commands_during_combat() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    registry = CommandRegistry()
    register_all_commands(registry)

    with Session(engine) as session:
        player = Player(
            id="player-1",
            username="petem",
            current_room_id="tavern",
            respawn_room_id="tavern",
            active_combat_session_id="combat-1",
        )
        ctx = _build_context(session, player=player)

        registry.get("help").handler(None, ctx)

    assert ctx.messages[0].startswith("You are in combat.")
    assert "go <direction>" not in ctx.messages[0]
    assert "take <item>" not in ctx.messages[0]
    assert "help — show this list" in ctx.messages[0]


def test_help_respects_room_disabled_commands() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    registry = CommandRegistry()
    register_all_commands(registry)

    with Session(engine) as session:
        room = Room(
            id="tavern",
            name="Tavern",
            description="A warm room.",
            map_x=0,
            map_y=0,
            disabled_commands=["take"],
        )
        ctx = _build_context(session, room=room)

        registry.get("help").handler(None, ctx)

    assert "take <item>" not in ctx.messages[0]
    assert "drop <item>" in ctx.messages[0]


def _build_context(
    session: Session, *, player: Player | None = None, room: Room | None = None
) -> GameContext:
    player = player or Player(
        id="player-1",
        username="petem",
        current_room_id="tavern",
        respawn_room_id="tavern",
    )
    room = room or Room(
        id="tavern",
        name="Tavern",
        description="A warm room.",
        map_x=0,
        map_y=0,
    )
    return GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(
            actor_id="player-1", correlation_id="session-1"
        ),
        session_id="session-1",
    )
