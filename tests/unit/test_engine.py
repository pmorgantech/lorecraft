from types import SimpleNamespace

from lorecraft.game.context import GameContext
from lorecraft.game.engine import CommandEngine
from lorecraft.game.events import EventBus
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rules import RuleEngine, RuleResult
from lorecraft.game.transaction import TransactionContext


def build_context() -> GameContext:
    return GameContext(
        player=SimpleNamespace(id="player-1", flags={}, inventory=[], active_combat_session_id=None),
        room=SimpleNamespace(id="tavern", disabled_commands=[], light_level=1),
        clock=SimpleNamespace(game_epoch=0),
        player_repo=None,
        room_repo=None,
        item_repo=None,
        npc_repo=None,
        manager=None,
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id="player-1", correlation_id="session-1"),
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
    rules.register_rule("take", lambda ctx, payload: RuleResult.block("The artifact resists you."))
    ctx = build_context()

    CommandEngine(registry, rules).handle_command("take gem", ctx)

    assert ctx.messages == ["The artifact resists you."]
