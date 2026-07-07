"""Sprint 55.1: object_present / npc_present command-condition gates."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.command_conditions import get_registry
from lorecraft.engine.game.holders import Location
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import NPC, Item, Room
from tests.unit.test_marks_service import _ctx


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        yield session


def _seed(session: Session) -> Player:
    session.add(Room(id="square", name="Square", description="d", map_x=0, map_y=0))
    session.add(Room(id="void", name="Void", description="d", map_x=9, map_y=9))
    session.add(Item(id="lever", name="Iron Lever", description="d", takeable=False))
    session.add(Item(id="sundial", name="Brass Sundial", description="d"))
    player = Player(
        id="p1", username="Tinker", current_room_id="square", respawn_room_id="square"
    )
    session.add(player)
    session.add(PlayerStats(player_id="p1"))
    session.commit()
    return player


class TestObjectPresent:
    def test_true_when_item_in_room(self, session: Session) -> None:
        player = _seed(session)
        ctx = _ctx(session, player)
        ctx.item_location.spawn("lever", Location("room", "square"))
        session.commit()
        assert get_registry().evaluate("object_present:lever", ctx).allowed is True

    def test_true_when_item_held(self, session: Session) -> None:
        player = _seed(session)
        ctx = _ctx(session, player)
        ctx.item_location.spawn("sundial", Location("player", "p1"))
        session.commit()
        assert get_registry().evaluate("object_present:sundial", ctx).allowed is True

    def test_false_when_item_elsewhere(self, session: Session) -> None:
        player = _seed(session)
        ctx = _ctx(session, player)
        ctx.item_location.spawn("lever", Location("room", "void"))
        session.commit()
        result = get_registry().evaluate("object_present:lever", ctx)
        assert result.allowed is False
        assert result.reason == "There's nothing like that here."

    def test_false_with_empty_param(self, session: Session) -> None:
        player = _seed(session)
        ctx = _ctx(session, player)
        assert get_registry().evaluate("object_present", ctx).allowed is False


class TestNpcPresent:
    def test_true_when_npc_in_room(self, session: Session) -> None:
        player = _seed(session)
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
        ctx = _ctx(session, player)
        assert get_registry().evaluate("npc_present:dog", ctx).allowed is True

    def test_false_when_npc_elsewhere(self, session: Session) -> None:
        player = _seed(session)
        session.add(
            NPC(
                id="dog",
                name="Scruffy",
                description="d",
                current_room_id="void",
                home_room_id="void",
                dialogue_tree_id="",
            )
        )
        session.commit()
        ctx = _ctx(session, player)
        result = get_registry().evaluate("npc_present:dog", ctx)
        assert result.allowed is False
        assert result.reason == "They aren't here."

    def test_false_when_npc_unknown(self, session: Session) -> None:
        player = _seed(session)
        ctx = _ctx(session, player)
        assert get_registry().evaluate("npc_present:ghost", ctx).allowed is False
