from types import SimpleNamespace

from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine, RuleResult
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.models.audit import AuditEvent
from lorecraft.models.player import Player
from lorecraft.models.world import Item, Room
from lorecraft.engine.repos.audit_repo import AuditRepo
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService


def build_context() -> GameContext:
    return GameContext(
        player=SimpleNamespace(
            id="player-1", flags={}, inventory=[], active_combat_session_id=None
        ),
        room=SimpleNamespace(id="tavern", disabled_commands=[], light_level=1),
        clock=SimpleNamespace(game_epoch=0),
        session=None,
        player_repo=None,
        room_repo=None,
        item_repo=None,
        stack_repo=None,
        item_location=None,
        ledger=None,
        meters=None,
        effects=None,
        npc_repo=None,
        manager=None,
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(
            actor_id="player-1", correlation_id="session-1"
        ),
        session_id="session-1",
        rng=GameRng(),
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


def test_engine_rolls_back_and_records_command_failed_on_handler_crash() -> None:
    game_engine = create_engine("sqlite://")
    audit_engine = create_engine("sqlite://")
    create_tables(game_engine=game_engine, audit_engine=audit_engine)

    registry = CommandRegistry()

    @registry.register("break")
    def break_handler(noun, ctx):
        ctx.say("You start to break the vase...")
        ctx.item_location.spawn("shard", Location("player", ctx.player.id))
        raise RuntimeError("vase shattered unexpectedly")

    with Session(game_engine) as game_session, Session(audit_engine) as audit_session:
        game_session.add(Item(id="shard", name="Shard", description="A shard."))
        game_session.commit()
        ctx = build_persistent_context(game_session, audit_session)

        parsed = CommandEngine(registry, RuleEngine()).handle_command("break", ctx)

        events = audit_session.exec(select(AuditEvent)).all()

    # Partial narration/state from before the crash must not reach the client.
    assert parsed.verb == "break"
    assert ctx.messages == ["Something went wrong processing that command."]
    assert ctx.room_messages == []
    assert ctx.updates == {}

    assert len(events) == 1
    assert events[0].event_type == "command_failed"
    assert events[0].severity == "ERROR"
    assert events[0].payload_json["reason_type"] == "handler_exception"
    assert events[0].payload_json["error_type"] == "RuntimeError"

    # The game DB session was rolled back — the player row committed by
    # build_persistent_context() is visible, but the in-flight stack spawn
    # the crashed handler made was never persisted.
    with Session(game_engine) as verify_session:
        persisted_player = verify_session.get(Player, "player-1")
        assert persisted_player is not None
        assert StackRepo(verify_session).stacks_for_owner("player", "player-1") == []


def test_engine_isolates_multiple_commands_from_one_crash() -> None:
    """A crash in one chained command shouldn't stop the rest from running."""
    game_engine = create_engine("sqlite://")
    audit_engine = create_engine("sqlite://")
    create_tables(game_engine=game_engine, audit_engine=audit_engine)

    registry = CommandRegistry()

    @registry.register("boom")
    def boom(noun, ctx):
        raise RuntimeError("boom")

    @registry.register("look")
    def look(noun, ctx):
        ctx.say("The tavern is quiet.")

    with Session(game_engine) as game_session, Session(audit_engine) as audit_session:
        ctx = build_persistent_context(game_session, audit_session)

        CommandEngine(registry, RuleEngine()).handle_command("boom; look", ctx)

    assert ctx.messages == [
        "Something went wrong processing that command.",
        "The tavern is quiet.",
    ]


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
        session=game_session,
        player_repo=PlayerRepo(game_session),
        room_repo=RoomRepo(game_session),
        item_repo=ItemRepo(game_session),
        stack_repo=StackRepo(game_session),
        item_location=ItemLocationService(game_session),
        ledger=LedgerService(),
        meters=MeterService(game_session.get_bind(), GameRng()),
        effects=EffectService(game_session.get_bind(), GameRng()),
        npc_repo=NpcRepo(game_session),
        manager=SimpleNamespace(),
        bus=EventBus(),
        audit=AuditRepo(audit_session),
        transaction=TransactionContext.create(
            actor_id="player-1", correlation_id="session-1"
        ),
        session_id="session-1",
        rng=GameRng(),
        commit_state=game_session.commit,
        commit_audit=audit_session.commit,
        rollback_state=game_session.rollback,
    )
