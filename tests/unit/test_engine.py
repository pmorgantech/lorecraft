from types import SimpleNamespace

from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.game.context import GameContext
from lorecraft.game.engine import CommandEngine
from lorecraft.game.events import EventBus
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rules import RuleEngine, RuleResult
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.audit import AuditEvent
from lorecraft.models.player import Player
from lorecraft.models.world import Room
from lorecraft.repos.audit_repo import AuditRepo
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo


def build_context() -> GameContext:
    return GameContext(
        player=SimpleNamespace(
            id="player-1", flags={}, inventory=[], active_combat_session_id=None
        ),
        room=SimpleNamespace(id="tavern", disabled_commands=[], light_level=1),
        clock=SimpleNamespace(game_epoch=0),
        player_repo=None,
        room_repo=None,
        item_repo=None,
        npc_repo=None,
        manager=None,
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(
            actor_id="player-1", correlation_id="session-1"
        ),
        session_id="session-1",
    )


def test_engine_dispatches_registered_command() -> None:
    registry = CommandRegistry()

    @registry.register("look")
    def look(noun, ctx):
        ctx.say("The tavern is quiet.")

    ctx = build_context()
    parsed = CommandEngine(registry, RuleEngine()).handle_command("look", ctx)

    assert parsed.verb == "look"
    assert ctx.messages == ["The tavern is quiet."]


def test_engine_blocks_unknown_command() -> None:
    ctx = build_context()

    CommandEngine(CommandRegistry(), RuleEngine()).handle_command("xyzzy", ctx)

    assert ctx.messages == ["I don't understand that command."]


def test_engine_checks_rules_before_handler() -> None:
    registry = CommandRegistry()

    @registry.register("take")
    def take(noun, ctx):
        raise AssertionError("handler should not run")

    rules = RuleEngine()
    rules.register_rule(
        "take", lambda ctx, payload: RuleResult.block("The artifact resists you.")
    )
    ctx = build_context()

    CommandEngine(registry, rules).handle_command("take gem", ctx)

    assert ctx.messages == ["The artifact resists you."]


def test_engine_records_blocked_command_audit_event() -> None:
    game_engine = create_engine("sqlite://")
    audit_engine = create_engine("sqlite://")
    create_tables(game_engine=game_engine, audit_engine=audit_engine)

    with Session(game_engine) as game_session, Session(audit_engine) as audit_session:
        ctx = build_persistent_context(game_session, audit_session)

        CommandEngine(CommandRegistry(), RuleEngine()).handle_command("xyzzy", ctx)

        events = audit_session.exec(select(AuditEvent)).all()

    assert ctx.messages == ["I don't understand that command."]
    assert len(events) == 1
    assert events[0].event_type == "command_blocked"
    assert events[0].severity == "WARNING"
    assert events[0].payload_json["reason_type"] == "unknown_command"


def test_engine_records_duration_ms_on_successful_command_audit_event() -> None:
    game_engine = create_engine("sqlite://")
    audit_engine = create_engine("sqlite://")
    create_tables(game_engine=game_engine, audit_engine=audit_engine)

    registry = CommandRegistry()

    @registry.register("look")
    def look(noun, ctx):
        ctx.say("The tavern is quiet.")

    with Session(game_engine) as game_session, Session(audit_engine) as audit_session:
        ctx = build_persistent_context(game_session, audit_session)

        CommandEngine(registry, RuleEngine()).handle_command("look", ctx)

        events = audit_session.exec(select(AuditEvent)).all()

    assert len(events) == 1
    assert events[0].event_type == "command_executed"
    duration_ms = events[0].payload_json["duration_ms"]
    assert isinstance(duration_ms, (int, float))
    assert duration_ms >= 0.0


def build_persistent_context(
    game_session: Session, audit_session: Session
) -> GameContext:
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
    game_session.add(player)
    game_session.add(room)
    game_session.commit()
    return GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(game_session),
        room_repo=RoomRepo(game_session),
        item_repo=ItemRepo(game_session),
        npc_repo=NpcRepo(game_session),
        manager=SimpleNamespace(),
        bus=EventBus(),
        audit=AuditRepo(audit_session),
        transaction=TransactionContext.create(
            actor_id="player-1", correlation_id="session-1"
        ),
        session_id="session-1",
        commit_audit=audit_session.commit,
    )
