"""Sprint 55.3: context-command dispatcher — gating, firing, disambiguation."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Item, Room
from lorecraft.features.context_commands.commands import register_context_commands
from lorecraft.features.context_commands.models import (
    ContextBinding,
    ContextCommandRegistry,
)
from tests.unit.test_marks_service import _ctx


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        yield session


def _seed(session: Session) -> Player:
    session.add(Room(id="square", name="Square", description="d", map_x=0, map_y=0))
    session.add(Item(id="lever", name="Iron Lever", description="d", takeable=False))
    session.add(Item(id="rusty", name="Rusty Lever", description="d", takeable=False))
    session.add(Item(id="brass", name="Brass Lever", description="d", takeable=False))
    player = Player(
        id="p1", username="Tinker", current_room_id="square", respawn_room_id="square"
    )
    session.add(player)
    session.add(PlayerStats(player_id="p1"))
    session.commit()
    return player


def _binding(
    verb: str,
    owner_id: str,
    *,
    say: str = "",
    side_effects: dict | None = None,
    aliases: tuple[str, ...] = (),
    owner_type: str = "item",
    requires: str | None = None,
) -> ContextBinding:
    return ContextBinding(
        verb=verb,
        owner_type=owner_type,
        owner_id=owner_id,
        aliases=aliases,
        help="",
        say=say,
        side_effects=side_effects or {},
        requires=requires,
    )


def _ctx_reg(*bindings: ContextBinding) -> ContextCommandRegistry:
    reg = ContextCommandRegistry()
    for binding in bindings:
        reg.register(binding)
    return reg


def test_verb_registered_and_gated_by_presence(session: Session) -> None:
    player = _seed(session)
    cmd = CommandRegistry()
    register_context_commands(cmd, _ctx_reg(_binding("pull", "lever", say="Clunk.")))

    command = cmd.get("pull")
    assert command is not None

    ctx = _ctx(session, player)
    # Lever not present → the context_verb condition blocks it.
    assert cmd.evaluate_conditions(command, ctx).allowed is False

    ctx.item_location.spawn("lever", Location("room", "square"))
    session.commit()
    assert cmd.evaluate_conditions(command, ctx).allowed is True


def test_handler_fires_say_and_side_effects(session: Session) -> None:
    player = _seed(session)
    cmd = CommandRegistry()
    register_context_commands(
        cmd,
        _ctx_reg(
            _binding(
                "pull",
                "lever",
                say="The lever clunks down.",
                side_effects={"set_flags": ["lever_pulled"]},
            )
        ),
    )
    ctx = _ctx(session, player)
    ctx.item_location.spawn("lever", Location("room", "square"))
    session.commit()

    cmd.get("pull").handler(None, ctx)

    assert "The lever clunks down." in ctx.messages
    assert ctx.player.flags.get("lever_pulled") is True


def test_noun_disambiguates_shared_verb(session: Session) -> None:
    player = _seed(session)
    cmd = CommandRegistry()
    register_context_commands(
        cmd,
        _ctx_reg(
            _binding("pull", "rusty", side_effects={"set_flags": ["rusty_done"]}),
            _binding("pull", "brass", side_effects={"set_flags": ["brass_done"]}),
        ),
    )
    ctx = _ctx(session, player)
    ctx.item_location.spawn("rusty", Location("room", "square"))
    ctx.item_location.spawn("brass", Location("room", "square"))
    session.commit()

    cmd.get("pull").handler("rusty", ctx)

    assert ctx.player.flags.get("rusty_done") is True
    assert ctx.player.flags.get("brass_done") is None


def test_collision_with_builtin_is_skipped(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    cmd = CommandRegistry()

    @cmd.register("look", help="the real look")
    def _look(noun: str | None, ctx: object) -> None:  # pragma: no cover
        pass

    with caplog.at_level(logging.WARNING):
        register_context_commands(
            cmd, _ctx_reg(_binding("look", "lever", say="hijacked"))
        )

    # The built-in survives; the context verb was skipped with a warning.
    assert cmd.get("look").help_text == "the real look"
    assert any("shadows" in r.message for r in caplog.records)


def test_npc_carried_verb(session: Session) -> None:
    player = _seed(session)
    from lorecraft.engine.models.world import NPC

    session.add(
        NPC(
            id="dog",
            name="Scruffy",
            description="d",
            current_room_id="square",
            home_room_id="square",
            dialogue_tree_id="",
        )
    )
    session.commit()
    cmd = CommandRegistry()
    register_context_commands(
        cmd,
        _ctx_reg(
            _binding("pet", "dog", owner_type="npc", say="Scruffy wags its tail.")
        ),
    )
    ctx = _ctx(session, player)
    command = cmd.get("pet")
    assert command is not None
    assert cmd.evaluate_conditions(command, ctx).allowed is True
    command.handler(None, ctx)
    assert "Scruffy wags its tail." in ctx.messages
