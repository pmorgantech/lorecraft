"""Unit tests for ItemLocationService — the Sprint 16 move primitive.

Exercises the invariants from engine_core.md §3.2: quantity floor, instanced
vs fungible stacking, atomic move semantics (split/merge), container cycle
prevention, and holder/move-validator dispatch.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.errors import ConflictError, NotFoundError, ValidationError
from lorecraft.game.components import ComponentDef
from lorecraft.game.components import get_registry as get_component_registry
from lorecraft.game.holders import Location
from lorecraft.game.holders import get_registry as get_holder_registry
from lorecraft.models.player import Player
from lorecraft.models.world import Item, Room
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.item_location import ItemLocationService


def _make_session() -> Session:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return Session(engine)


def _seed_world(session: Session) -> None:
    session.add(Room(id="room-1", name="Room One", description="d", map_x=0, map_y=0))
    session.add(Room(id="room-2", name="Room Two", description="d", map_x=1, map_y=0))
    session.add(
        Player(
            id="player-1",
            username="p1",
            current_room_id="room-1",
            respawn_room_id="room-1",
        )
    )
    session.add(Item(id="coin", name="Coin", description="A coin."))
    session.add(Item(id="sword", name="Sword", description="A sword."))
    session.commit()


@pytest.fixture
def session() -> Iterator[Session]:
    s = _make_session()
    _seed_world(s)
    yield s
    s.close()


@pytest.fixture
def instanced_component() -> Iterator[None]:
    """Registers a fake component so 'sword' items always instantiate."""
    registry = get_component_registry()
    registry.register(
        ComponentDef(
            name="__test_durability__",
            applies_to=lambda item: item.id == "sword",
            initial_state=lambda item: {"current": 100},
            validate=lambda state: [],
        )
    )
    yield
    registry._components.pop("__test_durability__", None)  # type: ignore[attr-defined]


class TestSpawn:
    def test_spawn_creates_fungible_stack(self, session: Session) -> None:
        service = ItemLocationService(session)
        stacks = service.spawn("coin", Location("player", "player-1"), 5)

        assert len(stacks) == 1
        assert stacks[0].quantity == 5
        assert stacks[0].instance_id is None

    def test_spawn_merges_into_existing_fungible_stack(self, session: Session) -> None:
        service = ItemLocationService(session)
        loc = Location("player", "player-1")
        service.spawn("coin", loc, 3)
        service.spawn("coin", loc, 2)

        stacks = StackRepo(session).stacks_for_owner("player", "player-1")
        assert len(stacks) == 1
        assert stacks[0].quantity == 5

    def test_spawn_rejects_quantity_under_one(self, session: Session) -> None:
        service = ItemLocationService(session)
        with pytest.raises(ValidationError):
            service.spawn("coin", Location("player", "player-1"), 0)

    def test_spawn_rejects_unknown_item(self, session: Session) -> None:
        service = ItemLocationService(session)
        with pytest.raises(NotFoundError):
            service.spawn("no-such-item", Location("player", "player-1"))

    def test_spawn_rejects_unknown_holder(self, session: Session) -> None:
        service = ItemLocationService(session)
        with pytest.raises(NotFoundError):
            service.spawn("coin", Location("player", "no-such-player"))

    def test_spawn_creates_one_instanced_stack_per_unit(
        self, session: Session, instanced_component: None
    ) -> None:
        service = ItemLocationService(session)
        stacks = service.spawn("sword", Location("room", "room-1"), 3)

        assert len(stacks) == 3
        for stack in stacks:
            assert stack.quantity == 1
            assert stack.instance_id is not None
        # Each instance is distinct.
        assert len({s.instance_id for s in stacks}) == 3


class TestDestroy:
    def test_destroy_reduces_quantity(self, session: Session) -> None:
        service = ItemLocationService(session)
        stack = service.spawn("coin", Location("player", "player-1"), 5)[0]

        assert stack.id is not None
        service.destroy(stack.id, 2)

        remaining = StackRepo(session).find_stack(stack.id)
        assert remaining is not None
        assert remaining.quantity == 3

    def test_destroy_deletes_stack_at_zero(self, session: Session) -> None:
        service = ItemLocationService(session)
        stack = service.spawn("coin", Location("player", "player-1"), 2)[0]

        assert stack.id is not None
        service.destroy(stack.id, 2)

        assert StackRepo(session).find_stack(stack.id) is None

    def test_destroy_rejects_quantity_underflow(self, session: Session) -> None:
        service = ItemLocationService(session)
        stack = service.spawn("coin", Location("player", "player-1"), 2)[0]

        assert stack.id is not None
        with pytest.raises(ConflictError):
            service.destroy(stack.id, 3)

    def test_destroy_rejects_unknown_stack(self, session: Session) -> None:
        service = ItemLocationService(session)
        with pytest.raises(NotFoundError):
            service.destroy(999999, 1)


class TestMaterialize:
    def test_materialize_splits_one_unit_into_new_instance(
        self, session: Session
    ) -> None:
        service = ItemLocationService(session)
        stack = service.spawn("coin", Location("player", "player-1"), 3)[0]

        assert stack.id is not None
        new_stack = service.materialize(stack.id)

        assert new_stack.quantity == 1
        assert new_stack.instance_id is not None

        source = StackRepo(session).find_stack(stack.id)
        assert source is not None
        assert source.quantity == 2

    def test_materialize_rejects_already_instanced_stack(
        self, session: Session, instanced_component: None
    ) -> None:
        service = ItemLocationService(session)
        stack = service.spawn("sword", Location("player", "player-1"), 1)[0]

        assert stack.id is not None
        with pytest.raises(ConflictError):
            service.materialize(stack.id)

    def test_materialize_rejects_insufficient_quantity(self, session: Session) -> None:
        service = ItemLocationService(session)
        stack = service.spawn("coin", Location("player", "player-1"), 1)[0]

        assert stack.id is not None
        with pytest.raises(ConflictError):
            service.materialize(stack.id)


class TestMove:
    def test_move_entire_fungible_stack(self, session: Session) -> None:
        service = ItemLocationService(session)
        stack = service.spawn("coin", Location("room", "room-1"), 3)[0]

        assert stack.id is not None
        dest = service.move(stack.id, Location("player", "player-1"), 3)

        assert dest.owner_type == "player"
        assert dest.owner_id == "player-1"
        assert dest.quantity == 3
        assert StackRepo(session).stacks_at(Location("room", "room-1")) == []

    def test_move_splits_partial_quantity(self, session: Session) -> None:
        service = ItemLocationService(session)
        stack = service.spawn("coin", Location("room", "room-1"), 5)[0]

        assert stack.id is not None
        dest = service.move(stack.id, Location("player", "player-1"), 2)

        assert dest.quantity == 2
        source = StackRepo(session).find_stack(stack.id)
        assert source is not None
        assert source.quantity == 3

    def test_move_merges_into_existing_fungible_dest_stack(
        self, session: Session
    ) -> None:
        service = ItemLocationService(session)
        room_stack = service.spawn("coin", Location("room", "room-1"), 2)[0]
        service.spawn("coin", Location("player", "player-1"), 4)

        assert room_stack.id is not None
        dest = service.move(room_stack.id, Location("player", "player-1"), 2)

        assert dest.quantity == 6
        player_stacks = StackRepo(session).stacks_for_owner("player", "player-1")
        assert len(player_stacks) == 1

    def test_move_rejects_quantity_exceeding_source(self, session: Session) -> None:
        service = ItemLocationService(session)
        stack = service.spawn("coin", Location("room", "room-1"), 2)[0]

        assert stack.id is not None
        with pytest.raises(ConflictError):
            service.move(stack.id, Location("player", "player-1"), 3)

    def test_move_rejects_unknown_destination_holder(self, session: Session) -> None:
        service = ItemLocationService(session)
        stack = service.spawn("coin", Location("room", "room-1"), 1)[0]

        assert stack.id is not None
        with pytest.raises(NotFoundError):
            service.move(stack.id, Location("player", "no-such-player"), 1)

    def test_move_instanced_stack_must_move_whole_unit(
        self, session: Session, instanced_component: None
    ) -> None:
        service = ItemLocationService(session)
        stack = service.spawn("sword", Location("room", "room-1"), 1)[0]

        assert stack.id is not None
        dest = service.move(stack.id, Location("player", "player-1"), 1)

        assert dest.instance_id == stack.instance_id
        assert dest.owner_type == "player"

    def test_move_container_cycle_is_rejected(
        self, session: Session, instanced_component: None
    ) -> None:
        service = ItemLocationService(session)
        # "sword" instantiates (fake component); use its own instance as both
        # the moved item and the destination container to trigger the cycle.
        stack = service.spawn("sword", Location("room", "room-1"), 1)[0]
        assert stack.id is not None
        assert stack.instance_id is not None

        with pytest.raises(ConflictError):
            service.move(stack.id, Location("container", stack.instance_id), 1)

    def test_move_runs_registered_holder_validators(self, session: Session) -> None:
        holder_registry = get_holder_registry()
        calls: list[tuple[str, int]] = []

        def _veto_everything(session_arg, dest, item, quantity) -> None:
            calls.append((item.id, quantity))
            raise ConflictError("blocked by test validator", "conflict_test_veto")

        holder_registry.register_move_validator("player", _veto_everything)
        try:
            service = ItemLocationService(session)
            stack = service.spawn("coin", Location("room", "room-1"), 1)[0]

            assert stack.id is not None
            with pytest.raises(ConflictError):
                service.move(stack.id, Location("player", "player-1"), 1)
            assert calls == [("coin", 1)]
        finally:
            holder_registry._move_validators["player"].remove(_veto_everything)  # type: ignore[attr-defined]


class TestItemRepoStackQueries:
    def test_items_in_room_reflects_spawned_stacks(self, session: Session) -> None:
        service = ItemLocationService(session)
        service.spawn("coin", Location("room", "room-1"), 4)
        service.spawn("sword", Location("room", "room-1"), 1)

        item_repo = ItemRepo(session)
        room_items = item_repo.items_in_room("room-1")

        assert {item.id for _stack, item in room_items} == {"coin", "sword"}

    def test_stacks_carried_by_reflects_player_stacks(self, session: Session) -> None:
        service = ItemLocationService(session)
        service.spawn("coin", Location("player", "player-1"), 2)

        item_repo = ItemRepo(session)
        carried = item_repo.stacks_carried_by("player-1")

        assert len(carried) == 1
        stack, item = carried[0]
        assert item.id == "coin"
        assert stack.quantity == 2
