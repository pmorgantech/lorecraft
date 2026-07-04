"""Tests for containers (put/take from), nesting/capacity limits, and
light/darkness gating with equipped lit sources (Sprint 23.3)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

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
from lorecraft.models.player import Player, PlayerStats
from lorecraft.models.world import Room
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.effects import EffectService
from lorecraft.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.services.light_fuel import LightFuelService
from lorecraft.services.meters import MeterService
from lorecraft.world.loader import import_world
from lorecraft.world.validator import ItemData, RoomData, WorldDocument
from lorecraft.game.standard_components import register as _register_item_components
from lorecraft.game.container_validators import register as _register_containers
from lorecraft.game.equipment_validators import (
    register as _register_equipment_validators,
)

# Standard components + container/equipment move validators used to register as
# import side effects; they now register via their feature register()s.
_register_item_components()
_register_containers()
_register_equipment_validators()

ROOM_ID = "room-1"
DARK_ROOM_ID = "dark-room"


def _seed(session: Session) -> None:
    document = WorldDocument(
        rooms=[
            RoomData(id=ROOM_ID, name="Room One", description="d", map_x=0, map_y=0),
            RoomData(
                id=DARK_ROOM_ID,
                name="Dark Room",
                description="d",
                map_x=1,
                map_y=0,
                light_level=0,
            ),
        ],
        items=[
            ItemData(
                id="chest",
                name="wooden chest",
                description="A chest.",
                takeable=False,
                capacity=10.0,
            ),
            ItemData(
                id="pouch",
                name="small pouch",
                description="A pouch.",
                capacity=5.0,
                weight=0.5,
            ),
            ItemData(
                id="coin",
                name="coin",
                description="A coin.",
                weight=0.01,
            ),
            ItemData(
                id="heavy_rock",
                name="heavy rock",
                description="A rock.",
                weight=100.0,
            ),
            ItemData(
                id="lantern",
                name="brass lantern",
                description="A lantern.",
                slot="off_hand",
                wearable=False,
                weight=1.0,
                light=3,
                max_durability=10,
            ),
        ],
    )
    import_world(document, session)


def _build_engine_and_ctx(
    room_id: str = ROOM_ID,
) -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    _seed(session)
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=room_id,
        respawn_room_id=room_id,
    )
    session.add(player)
    session.add(PlayerStats(player_id=player.id))
    session.commit()

    room = session.get(Room, room_id)
    assert room is not None
    item_location = ItemLocationService(session)
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


class TestPutTake:
    def test_put_item_in_open_container(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        ctx.item_location.spawn("chest", Location("room", ROOM_ID))
        ctx.item_location.spawn("coin", Location("player", ctx.player.id))
        ctx.session.commit()

        cmd_engine.handle_command("open chest", ctx)
        ctx.messages.clear()
        cmd_engine.handle_command("put coin in chest", ctx)

        assert ctx.messages == ["You put the coin in the wooden chest."]

    def test_put_item_in_closed_container_fails(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        ctx.item_location.spawn("chest", Location("room", ROOM_ID))
        ctx.item_location.spawn("coin", Location("player", ctx.player.id))
        ctx.session.commit()

        cmd_engine.handle_command("put coin in chest", ctx)

        assert ctx.messages == ["The container is closed"]

    def test_put_exceeding_capacity_fails(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        ctx.item_location.spawn("pouch", Location("room", ROOM_ID))
        ctx.item_location.spawn("heavy_rock", Location("player", ctx.player.id))
        ctx.session.commit()

        cmd_engine.handle_command("open pouch", ctx)
        ctx.messages.clear()
        cmd_engine.handle_command("put heavy rock in pouch", ctx)

        assert ctx.messages == ["The container doesn't have room for that"]

    def test_take_from_container(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        ctx.item_location.spawn("chest", Location("room", ROOM_ID))
        ctx.item_location.spawn("coin", Location("player", ctx.player.id))
        ctx.session.commit()

        cmd_engine.handle_command("open chest", ctx)
        ctx.messages.clear()
        cmd_engine.handle_command("put coin in chest", ctx)
        ctx.messages.clear()
        cmd_engine.handle_command("take coin from chest", ctx)

        assert ctx.messages == ["You take the coin from the wooden chest."]
        stacks = ctx.stack_repo.stacks_for_owner("player", ctx.player.id)
        assert any(s.slot is None for s in stacks)

    def test_take_from_closed_container_fails(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        ctx.item_location.spawn("chest", Location("room", ROOM_ID))
        ctx.item_location.spawn("coin", Location("player", ctx.player.id))
        ctx.session.commit()

        cmd_engine.handle_command("open chest", ctx)
        ctx.messages.clear()
        cmd_engine.handle_command("put coin in chest", ctx)
        ctx.messages.clear()
        cmd_engine.handle_command("close chest", ctx)
        ctx.messages.clear()
        cmd_engine.handle_command("take coin from chest", ctx)

        assert ctx.messages == ["The wooden chest is closed."]

    def test_nesting_beyond_max_depth_rejected(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        # Three chests nested inside each other (at max depth); a fourth
        # pouch can't go inside the innermost one.
        ctx.item_location.spawn("chest", Location("room", ROOM_ID))
        ctx.item_location.spawn("chest", Location("room", ROOM_ID))
        ctx.item_location.spawn("chest", Location("room", ROOM_ID))
        ctx.item_location.spawn("pouch", Location("player", ctx.player.id))
        session.commit()

        stacks = ctx.item_repo.items_in_room(ROOM_ID)
        chest_instances = [s.instance_id for s, _ in stacks if s.instance_id]
        assert len(chest_instances) == 3

        for instance_id in chest_instances:
            instance = session.get(ItemInstance, instance_id)
            assert instance is not None
            instance.state = {**instance.state, "openable": {"open": True}}
            session.add(instance)
        session.commit()

        # Nest chest[1] inside chest[0], chest[2] inside chest[1].
        outer_stack = next(s for s, _ in stacks if s.instance_id == chest_instances[0])
        middle_stack = next(s for s, _ in stacks if s.instance_id == chest_instances[1])
        assert middle_stack.id is not None
        ctx.item_location.move(
            middle_stack.id, Location("container", chest_instances[0]), 1
        )
        session.commit()
        inner_stacks = ctx.stack_repo.stacks_at(
            Location("container", chest_instances[0])
        )
        del outer_stack
        inner_chest_stack = next(
            s for s in inner_stacks if s.instance_id == chest_instances[1]
        )
        innermost_stack = next(
            s for s, _ in stacks if s.instance_id == chest_instances[2]
        )
        assert innermost_stack.id is not None
        ctx.item_location.move(
            innermost_stack.id, Location("container", inner_chest_stack.instance_id), 1
        )
        session.commit()

        # chest[2] is now at depth 2 (inside chest[1] inside chest[0]).
        # Putting the pouch inside it would put the pouch at depth 3, which
        # is allowed (MAX_NESTING_DEPTH=3); one level deeper is rejected.
        pouch_stacks = ctx.item_repo.player_stacks_matching(ctx.player.id, "pouch")
        pouch_stack = pouch_stacks[0][0]
        assert pouch_stack.id is not None
        ctx.item_location.move(
            pouch_stack.id, Location("container", chest_instances[2]), 1
        )
        session.commit()

        # Now try nesting a 4th chest inside the pouch -- exceeds max depth.
        ctx.item_location.spawn("chest", Location("player", ctx.player.id))
        session.commit()
        from lorecraft.errors import ConflictError

        fourth_chest_stack = ctx.item_repo.player_stacks_matching(
            ctx.player.id, "chest"
        )[0][0]
        assert fourth_chest_stack.id is not None
        with pytest.raises(ConflictError):
            ctx.item_location.move(
                fourth_chest_stack.id, Location("container", pouch_stack.instance_id), 1
            )


class TestLightAndDarkness:
    def test_dark_room_blocks_light_gated_command(self) -> None:
        cmd_engine, ctx, _session = _build_engine_and_ctx(DARK_ROOM_ID)

        cmd_engine.handle_command("look", ctx)

        assert ctx.messages == ["It's too dark to do that. You need a light."]

    def test_equipped_lit_lantern_allows_light_gated_command(self) -> None:
        cmd_engine, ctx, session = _build_engine_and_ctx(DARK_ROOM_ID)
        ctx.item_location.spawn("lantern", Location("player", ctx.player.id))
        session.commit()
        cmd_engine.handle_command("wield brass lantern", ctx)
        ctx.messages.clear()
        cmd_engine.handle_command("light brass lantern", ctx)
        ctx.messages.clear()

        cmd_engine.handle_command("look", ctx)

        assert ctx.messages != ["It's too dark to do that. You need a light."]

    def test_unlit_equipped_lantern_does_not_grant_light(self) -> None:
        cmd_engine, ctx, session = _build_engine_and_ctx(DARK_ROOM_ID)
        ctx.item_location.spawn("lantern", Location("player", ctx.player.id))
        session.commit()
        cmd_engine.handle_command("wield brass lantern", ctx)
        ctx.messages.clear()

        cmd_engine.handle_command("look", ctx)

        assert ctx.messages == ["It's too dark to do that. You need a light."]

    def test_light_and_extinguish_commands(self) -> None:
        cmd_engine, ctx, session = _build_engine_and_ctx()
        ctx.item_location.spawn("lantern", Location("player", ctx.player.id))
        session.commit()

        cmd_engine.handle_command("light brass lantern", ctx)
        assert ctx.messages == ["You light the brass lantern."]
        ctx.messages.clear()

        cmd_engine.handle_command("light brass lantern", ctx)
        assert ctx.messages == ["The brass lantern is already lit."]
        ctx.messages.clear()

        cmd_engine.handle_command("extinguish brass lantern", ctx)
        assert ctx.messages == ["You extinguish the brass lantern."]
        ctx.messages.clear()

        cmd_engine.handle_command("extinguish brass lantern", ctx)
        assert ctx.messages == ["The brass lantern isn't lit."]


class TestLightFuelDrain:
    def test_lit_lantern_drains_durability_on_tick(self) -> None:
        _cmd_engine, ctx, session = _build_engine_and_ctx()
        ctx.item_location.spawn("lantern", Location("player", ctx.player.id))
        session.commit()

        stack = ctx.item_repo.player_stacks_matching(ctx.player.id, "lantern")[0][0]
        instance = session.get(ItemInstance, stack.instance_id)
        assert instance is not None
        instance.state = {**instance.state, "lit": {"lit": True}}
        session.add(instance)
        session.commit()

        service = LightFuelService(session.get_bind())
        from lorecraft.game.events import Event, GameEvent

        service._on_time_advanced(Event(GameEvent.TIME_ADVANCED, {}), None)

        session.refresh(instance)
        assert instance.state["durability"]["current"] == 9

    def test_lantern_extinguishes_at_zero_durability(self) -> None:
        _cmd_engine, ctx, session = _build_engine_and_ctx()
        ctx.item_location.spawn("lantern", Location("player", ctx.player.id))
        session.commit()

        stack = ctx.item_repo.player_stacks_matching(ctx.player.id, "lantern")[0][0]
        instance = session.get(ItemInstance, stack.instance_id)
        assert instance is not None
        instance.state = {
            **instance.state,
            "lit": {"lit": True},
            "durability": {"current": 1},
        }
        session.add(instance)
        session.commit()

        service = LightFuelService(session.get_bind())
        from lorecraft.game.events import Event, GameEvent

        service._on_time_advanced(Event(GameEvent.TIME_ADVANCED, {}), None)

        session.refresh(instance)
        assert instance.state["durability"]["current"] == 0
        assert instance.state["lit"]["lit"] is False
