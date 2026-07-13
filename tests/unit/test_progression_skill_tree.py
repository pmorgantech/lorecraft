"""Skill-tree purchase service + train/abilities commands (Sprint 74.3 / 74.8)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus
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
from lorecraft.features.progression.service import SkillTreeService
from lorecraft.features.progression.skill_tree import (
    SkillTreeRegistry,
    ability_flag,
    validate_skill_tree_document,
)

ROOM_ID = "start"


def _registry() -> SkillTreeRegistry:
    doc = validate_skill_tree_document(
        {
            "nodes": [
                {"id": "forage", "name": "Forage", "cost": 1, "unlock": {}},
                {
                    "id": "sharp_eyes",
                    "name": "Sharp Eyes",
                    "cost": 2,
                    "prerequisites": ["forage"],
                    "unlock": {
                        "modifier": {
                            "key": "skill.perception",
                            "kind": "mult",
                            "amount": 1.1,
                        }
                    },
                },
            ]
        }
    )
    registry = SkillTreeRegistry()
    registry.load_document(doc)
    return registry


def _build_ctx(session: Session, *, skill_points: int) -> GameContext:
    session.add(Room(id=ROOM_ID, name="Start", description="d", map_x=0, map_y=0))
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=ROOM_ID,
        respawn_room_id=ROOM_ID,
    )
    session.add(player)
    session.add(PlayerStats(player_id=player.id, skill_points=skill_points))
    session.commit()
    room = session.get(Room, ROOM_ID)
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
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id=player.id, correlation_id="s1"),
        session_id="s1",
    )


@pytest.fixture
def ctx() -> Iterator[GameContext]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    yield _build_ctx(session, skill_points=3)
    session.close()


def test_purchase_spends_points_records_node_and_sets_flag(ctx: GameContext) -> None:
    service = SkillTreeService(_registry())

    result = service.purchase(ctx, "forage")

    assert result.ok
    stats = ctx.player_repo.stats(ctx.player.id)
    assert stats.skill_points == 2
    assert stats.unlocked_nodes == ["forage"]
    assert ctx.player.flags.get(ability_flag("forage")) is True


def test_purchase_rejects_unknown_node(ctx: GameContext) -> None:
    result = SkillTreeService(_registry()).purchase(ctx, "flight")
    assert not result.ok
    assert "no ability" in result.reason.lower()


def test_purchase_rejects_when_already_owned(ctx: GameContext) -> None:
    service = SkillTreeService(_registry())
    assert service.purchase(ctx, "forage").ok
    again = service.purchase(ctx, "forage")
    assert not again.ok
    assert "already" in again.reason.lower()


def test_purchase_rejects_unmet_prerequisite(ctx: GameContext) -> None:
    result = SkillTreeService(_registry()).purchase(ctx, "sharp_eyes")
    assert not result.ok
    assert "forage" in result.reason.lower()


def test_purchase_rejects_insufficient_points() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        ctx = _build_ctx(session, skill_points=0)
        result = SkillTreeService(_registry()).purchase(ctx, "forage")
    assert not result.ok
    assert "cost" in result.reason.lower()


def test_available_and_locked_partition(ctx: GameContext) -> None:
    service = SkillTreeService(_registry())
    available_ids = {n.id for n in service.available_nodes(ctx)}
    locked_ids = {n.id for n in service.locked_nodes(ctx)}
    # forage is affordable with no prereqs; sharp_eyes is prereq-locked.
    assert available_ids == {"forage"}
    assert locked_ids == {"sharp_eyes"}


def test_owned_moves_and_unlocks_dependent(ctx: GameContext) -> None:
    service = SkillTreeService(_registry())
    service.purchase(ctx, "forage")
    owned_ids = {n.id for n in service.owned_nodes(ctx)}
    available_ids = {n.id for n in service.available_nodes(ctx)}
    assert owned_ids == {"forage"}
    # With forage owned and 2 points left, sharp_eyes (cost 2) is now available.
    assert "sharp_eyes" in available_ids
