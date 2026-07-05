"""Unit tests for the `score` progress command (Sprint 34.2, issue-257c6643)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
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
from lorecraft.features.character.service import CharacterInfoService
from lorecraft.features.quests.models import PlayerQuestProgress

ROOM_ID = "room-1"


def _build_ctx() -> tuple[GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    session.add(Room(id=ROOM_ID, name="Room One", description="d", map_x=0, map_y=0))
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=ROOM_ID,
        respawn_room_id=ROOM_ID,
        visited_rooms=[ROOM_ID, "room-2", "room-3"],
        met_npcs=["mira"],
    )
    session.add(player)
    session.add(PlayerStats(player_id=player.id, level=3, xp=250, xp_to_next=400))
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
        transaction=TransactionContext.create(actor_id=player.id, correlation_id="s-1"),
        session_id="s-1",
    )
    return ctx, session


@pytest.fixture
def ctx_session() -> Iterator[tuple[GameContext, Session]]:
    ctx, session = _build_ctx()
    yield ctx, session
    session.close()


def test_score_command_is_registered() -> None:
    registry = CommandRegistry()
    register_all_commands(registry)
    assert registry.get("score") is not None


def test_score_reports_level_and_discoveries(
    ctx_session: tuple[GameContext, Session],
) -> None:
    ctx, _ = ctx_session
    CharacterInfoService().score(ctx)

    out = "\n".join(ctx.messages)
    assert "Level 3" in out
    assert "250/400 XP" in out
    # Three visited rooms, one NPC met.
    assert "3 rooms" in out
    assert "1 NPCs" in out


def test_score_push_update_payload(
    ctx_session: tuple[GameContext, Session],
) -> None:
    ctx, _ = ctx_session
    CharacterInfoService().score(ctx)

    payload = ctx.updates["score"]
    assert payload["level"] == 3
    assert payload["rooms_discovered"] == 3
    assert payload["npcs_met"] == 1
    assert payload["net_worth"] == 0  # no coins yet
    assert payload["quests_completed"] == 0


def test_score_counts_quests_and_wealth(
    ctx_session: tuple[GameContext, Session],
) -> None:
    ctx, session = ctx_session
    # One completed, one active quest.
    session.add(
        PlayerQuestProgress(
            player_id="player-1",
            quest_id="q1",
            current_stage_id="done",
            status="completed",
            started_at=0.0,
        )
    )
    session.add(
        PlayerQuestProgress(
            player_id="player-1",
            quest_id="q2",
            current_stage_id="s1",
            status="active",
            started_at=0.0,
        )
    )
    session.commit()
    # Give the player some coins via the ledger.
    ctx.ledger.credit(session, "player", "player-1", 42)
    session.commit()

    CharacterInfoService().score(ctx)
    payload = ctx.updates["score"]

    assert payload["quests_completed"] == 1
    assert payload["quests_active"] == 1
    assert payload["coins_carried"] == 42
    assert payload["net_worth"] == 42
