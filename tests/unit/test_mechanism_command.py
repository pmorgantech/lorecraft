"""Tests for the "mechanism" component and turn/pull/activate commands
(Sprint 30.2, docs/roadmap.md Sprint 30)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.items import ItemInstance
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Item, Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.item_components.components import (
    register as _register_item_components,
)

# Standard item components (mechanism, etc.) used to register as an import side
# effect; they now register via the item_components feature's register().
_register_item_components()

ROOM_ID = "room-1"


def _build_engine_and_ctx() -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    session.add(Room(id=ROOM_ID, name="Room One", description="d", map_x=0, map_y=0))
    session.add(
        Item(
            id="lever",
            name="brass lever",
            description="A stiff brass lever.",
            takeable=False,
            mechanism_states=["off", "on"],
            mechanism_side_effects={"on": {"set_flags": ["lever_pulled"]}},
        )
    )
    session.add(
        Item(
            id="dial",
            name="stone dial",
            description="A dial with four positions.",
            takeable=False,
            mechanism_states=["0", "1", "2", "3"],
            mechanism_side_effects={"3": {"set_flags": ["dial_solved"]}},
        )
    )
    session.add(Item(id="rock", name="rock", description="A rock.", takeable=False))
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=ROOM_ID,
        respawn_room_id=ROOM_ID,
    )
    session.add(player)
    session.commit()

    item_location = ItemLocationService(session)
    item_location.spawn("lever", Location("room", ROOM_ID))
    item_location.spawn("dial", Location("room", ROOM_ID))
    item_location.spawn("rock", Location("room", ROOM_ID))
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


def _mechanism_index(session: Session, item_repo: ItemRepo) -> int:
    stack, item = next(
        (s, i) for s, i in item_repo.items_in_room(ROOM_ID) if i.id == "lever"
    )
    instance = session.get(ItemInstance, stack.instance_id)
    assert instance is not None
    state = instance.state["mechanism"]
    assert isinstance(state, dict)
    return int(state["index"])


class TestMechanismComponent:
    def test_lever_spawns_with_mechanism_component_at_index_zero(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, _ctx, session = built
        assert _mechanism_index(session, ItemRepo(session)) == 0


class TestActivateCommand:
    def test_turn_cycles_lever_to_next_state(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built

        cmd_engine.handle_command("turn lever", ctx)

        assert any("clicks to 'on'" in m for m in ctx.messages)
        assert _mechanism_index(session, ItemRepo(session)) == 1

    def test_pull_and_activate_are_aliases(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built

        cmd_engine.handle_command("pull lever", ctx)
        assert _mechanism_index(session, ItemRepo(session)) == 1

        ctx.messages.clear()
        cmd_engine.handle_command("activate lever", ctx)
        assert _mechanism_index(session, ItemRepo(session)) == 0  # wraps back to "off"

    def test_lever_wraps_around_and_side_effect_fires_once_on_target(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("turn lever", ctx)  # -> "on": side effect fires
        assert ctx.player.flags.get("lever_pulled") is True

    def test_dial_needs_multiple_turns_to_reach_target_state(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("turn dial", ctx)  # 0 -> 1
        cmd_engine.handle_command("turn dial", ctx)  # 1 -> 2
        assert ctx.player.flags.get("dial_solved") is not True

        cmd_engine.handle_command("turn dial", ctx)  # 2 -> 3 (solved)
        assert ctx.player.flags.get("dial_solved") is True

    def test_activate_non_mechanism_item_reports_cannot(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("turn rock", ctx)

        assert any("can't activate" in m for m in ctx.messages)

    def test_activate_with_no_target_prompts(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("activate", ctx)

        assert ctx.messages == ["Activate what?"]
