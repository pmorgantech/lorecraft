from types import SimpleNamespace

from lorecraft.game.registry import CommandCondition, CommandRegistry


def test_registry_registers_primary_verb_and_aliases() -> None:
    registry = CommandRegistry()

    @registry.register("take", "get")
    def take(noun, ctx):
        ctx.say(noun)

    assert registry.get("take").handler is take
    assert registry.get("get").handler is take


def test_registry_blocks_disabled_room_command() -> None:
    registry = CommandRegistry()

    @registry.register("save")
    def save(noun, ctx):
        raise AssertionError("handler should not run")

    ctx = SimpleNamespace(
        room=SimpleNamespace(disabled_commands=["save"]), player=SimpleNamespace()
    )

    result = registry.evaluate_conditions(registry.get("save"), ctx)

    assert result.allowed is False
    assert result.reason == "You can't do that here."


def test_registry_evaluates_parameterized_flag_conditions() -> None:
    registry = CommandRegistry()

    @registry.register("open", conditions=[f"{CommandCondition.FLAG_SET}:cave_open"])
    def open_(noun, ctx):
        raise AssertionError("handler should not run")

    ctx = SimpleNamespace(
        room=SimpleNamespace(disabled_commands=[], light_level=1),
        player=SimpleNamespace(flags={"cave_open": False}),
    )

    result = registry.evaluate_conditions(registry.get("open"), ctx)

    assert result.allowed is False
    assert result.reason == "You can't do that yet."
