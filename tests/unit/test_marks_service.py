"""Sprint 53.2: MarkService — criteria evaluation, idempotent award, events."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.marks.models import (
    MarkRegistry,
    earned_flag,
    validate_marks_document,
)
from lorecraft.features.marks.service import MarkService

ROOM = "square"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        yield session


def _seed(session: Session) -> Player:
    session.add(Room(id=ROOM, name="Square", description="d", map_x=0, map_y=0))
    player = Player(
        id="p1", username="Walker", current_room_id=ROOM, respawn_room_id=ROOM
    )
    session.add(player)
    session.add(PlayerStats(player_id="p1"))
    session.commit()
    return player


def _ctx(session: Session, player: Player, bus: EventBus | None = None) -> GameContext:
    room = session.get(Room, player.current_room_id)
    assert room is not None
    return GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=GameRng(seed=1),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=bus or EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id="p1", correlation_id="s1"),
        session_id="s1",
    )


def _registry(*marks: dict[str, object]) -> MarkRegistry:
    registry = MarkRegistry()
    registry.load_document(validate_marks_document({"marks": list(marks)}))
    return registry


def _mark(
    mark_id: str, criteria: dict[str, object], **overrides: object
) -> dict[str, object]:
    base: dict[str, object] = {
        "id": mark_id,
        "name": f"Mark of {mark_id.title()}",
        "criteria": criteria,
    }
    base.update(overrides)
    return base


class TestCriteria:
    def test_rooms_visited_all_required(self, session: Session) -> None:
        player = _seed(session)
        service = MarkService(_registry(_mark("m", {"rooms_visited": [ROOM, "keep"]})))
        ctx = _ctx(session, player)

        player.visited_rooms = [ROOM]
        assert service.evaluate(ctx) == []
        player.visited_rooms = [ROOM, "keep"]
        assert [m.id for m in service.evaluate(ctx)] == ["m"]

    def test_rooms_visited_count(self, session: Session) -> None:
        player = _seed(session)
        service = MarkService(_registry(_mark("m", {"rooms_visited_count": 2})))
        ctx = _ctx(session, player)

        player.visited_rooms = [ROOM]
        assert service.evaluate(ctx) == []
        player.visited_rooms = [ROOM, "keep"]
        assert [m.id for m in service.evaluate(ctx)] == ["m"]

    def test_npcs_met_and_items_discovered(self, session: Session) -> None:
        player = _seed(session)
        service = MarkService(
            _registry(_mark("m", {"npcs_met": ["mira"], "items_discovered": ["coin"]}))
        )
        ctx = _ctx(session, player)

        player.met_npcs = ["mira"]
        assert service.evaluate(ctx) == []  # items still missing
        player.discovered_items = ["coin"]
        assert [m.id for m in service.evaluate(ctx)] == ["m"]

    def test_flags_set(self, session: Session) -> None:
        player = _seed(session)
        service = MarkService(_registry(_mark("m", {"flags_set": ["lore:tides"]})))
        ctx = _ctx(session, player)

        assert service.evaluate(ctx) == []
        player.flags = {"lore:tides": True}
        assert [m.id for m in service.evaluate(ctx)] == ["m"]


class TestAward:
    def test_award_sets_flag_and_announces(self, session: Session) -> None:
        player = _seed(session)
        service = MarkService(
            _registry(
                _mark(
                    "m",
                    {"rooms_visited": [ROOM]},
                    description="You walked the square.",
                )
            )
        )
        ctx = _ctx(session, player)
        player.visited_rooms = [ROOM]

        awarded = service.evaluate(ctx)

        assert [m.id for m in awarded] == ["m"]
        assert player.flags.get(earned_flag("m")) is True
        assert any("You have earned Mark of M!" in m for m in ctx.messages)
        assert any("You walked the square." in m for m in ctx.messages)

    def test_award_is_idempotent(self, session: Session) -> None:
        player = _seed(session)
        service = MarkService(_registry(_mark("m", {"rooms_visited": [ROOM]})))
        ctx = _ctx(session, player)
        player.visited_rooms = [ROOM]

        assert len(service.evaluate(ctx)) == 1
        assert service.evaluate(ctx) == []  # already earned — no re-award

    def test_chained_marks_award_in_one_pass(self, session: Session) -> None:
        """A mark whose criteria include another mark's earned flag resolves
        in the same evaluation (fixpoint loop)."""
        player = _seed(session)
        service = MarkService(
            _registry(
                _mark("meta", {"flags_set": [earned_flag("base")]}),
                _mark("base", {"rooms_visited": [ROOM]}),
            )
        )
        ctx = _ctx(session, player)
        player.visited_rooms = [ROOM]

        awarded = service.evaluate(ctx)

        assert {m.id for m in awarded} == {"base", "meta"}

    def test_earned_lists_only_earned(self, session: Session) -> None:
        player = _seed(session)
        service = MarkService(
            _registry(
                _mark("a", {"rooms_visited": [ROOM]}),
                _mark("b", {"rooms_visited": ["keep"]}),
            )
        )
        ctx = _ctx(session, player)
        player.visited_rooms = [ROOM]
        service.evaluate(ctx)

        assert [m.id for m in service.earned(player)] == ["a"]


class TestEvents:
    def test_award_rides_player_moved(self, session: Session) -> None:
        player = _seed(session)
        service = MarkService(_registry(_mark("m", {"rooms_visited": [ROOM]})))
        bus = EventBus()
        service.register(bus)
        ctx = _ctx(session, player, bus)
        player.visited_rooms = [ROOM]

        ctx.emit(GameEvent.PLAYER_MOVED, player_id="p1")
        ctx.flush_events()

        assert player.flags.get(earned_flag("m")) is True

    def test_non_game_context_ignored(self, session: Session) -> None:
        player = _seed(session)
        registry = _registry(_mark("m", {"rooms_visited": [ROOM]}))
        service = MarkService(registry)
        bus = EventBus()
        service.register(bus)
        player.visited_rooms = [ROOM]

        from lorecraft.engine.game.events import Event

        bus.emit(Event(GameEvent.PLAYER_MOVED, {"player_id": "p1"}), ctx=object())

        assert player.flags.get(earned_flag("m")) is None
