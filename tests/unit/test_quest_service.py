"""Unit tests for QuestService progression."""

from __future__ import annotations

import time

from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.events import Event, EventBus, GameEvent
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player
from lorecraft.models.quest import PlayerQuestProgress, Quest
from lorecraft.models.world import Room
from lorecraft.npc.dialogue import _start_quest
from lorecraft.repos.dialogue_repo import DialogueRepo
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.game.rng import GameRng
from lorecraft.services.effects import EffectService
from lorecraft.services.meters import MeterService
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.quest_repo import QuestRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.services.quest import QuestService


def _engine():
    e = create_engine("sqlite://")
    create_tables(game_engine=e, audit_engine=create_engine("sqlite://"))
    return e


def _seed(session: Session, *, visited_rooms: list[str] | None = None) -> Player:
    session.add(
        Room(id="tavern", name="Tavern", description="A warm room.", map_x=0, map_y=0)
    )
    session.add(
        Room(id="square", name="Square", description="A busy square.", map_x=1, map_y=0)
    )
    player = Player(
        id="p1",
        username="hero",
        current_room_id="tavern",
        respawn_room_id="tavern",
        visited_rooms=visited_rooms or ["tavern"],
    )
    session.add(player)
    session.add(
        Quest(
            id="q1",
            title="Visit the Square",
            description="Go east.",
            stages=[
                {
                    "id": "stage1",
                    "description": "Visit the square.",
                    "conditions": [{"type": "room_visited", "room_id": "square"}],
                    "completion_flags": {"visited_square": True},
                    "rewards": {"xp": 10},
                }
            ],
        )
    )
    return player


def _ctx(session: Session, player: Player) -> GameContext:
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
        rng=GameRng(),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        quest_repo=QuestRepo(session),
        dialogue_repo=DialogueRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id=player.id, correlation_id="s"),
        session_id="s",
    )


def test_start_quest_creates_progress() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session)
        session.commit()
        ctx = _ctx(session, player)

        _start_quest("q1", ctx)
        session.commit()

        progress = ctx.quest_repo.player_progress("p1", "q1")

    assert progress is not None
    assert progress.status == "active"
    assert progress.current_stage_id == "stage1"
    assert any("Quest started" in m for m in ctx.messages)


def test_start_quest_idempotent() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session)
        session.commit()
        ctx = _ctx(session, player)

        _start_quest("q1", ctx)
        _start_quest("q1", ctx)
        session.commit()

        all_progress = session.exec(
            select(PlayerQuestProgress).where(PlayerQuestProgress.player_id == "p1")
        ).all()

    assert len(all_progress) == 1


def test_check_progression_no_advance_when_condition_unmet() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session)
        session.commit()
        ctx = _ctx(session, player)
        _start_quest("q1", ctx)
        session.commit()

        QuestService().check_progression(Event(GameEvent.PLAYER_MOVED, {}), ctx)
        session.commit()

        progress = ctx.quest_repo.player_progress("p1", "q1")

    assert progress is not None
    assert progress.status == "active"
    assert not any("Quest completed" in m for m in ctx.messages)


def test_check_progression_completes_when_room_visited() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session, visited_rooms=["tavern", "square"])
        session.commit()
        ctx = _ctx(session, player)
        _start_quest("q1", ctx)
        ctx.messages.clear()
        session.commit()

        QuestService().check_progression(Event(GameEvent.PLAYER_MOVED, {}), ctx)
        session.commit()

        progress = ctx.quest_repo.player_progress("p1", "q1")
        player_flags = dict(player.flags)

    assert progress is not None
    assert progress.status == "completed"
    assert player_flags.get("visited_square") is True
    assert any("Quest completed" in m for m in ctx.messages)
    quest_update = ctx.updates.get("quest_update")
    assert isinstance(quest_update, dict)
    assert quest_update["status"] == "completed"


def test_check_progression_skips_non_game_context() -> None:
    QuestService().check_progression(Event(GameEvent.PLAYER_MOVED, {}), None)
    QuestService().check_progression(Event(GameEvent.PLAYER_MOVED, {}), "not-a-ctx")


def test_check_progression_flag_set_condition() -> None:
    e = _engine()
    with Session(e) as session:
        session.add(Room(id="r1", name="R1", description="X.", map_x=0, map_y=0))
        player = Player(
            id="p2",
            username="hero2",
            current_room_id="r1",
            respawn_room_id="r1",
        )
        session.add(player)
        session.add(
            Quest(
                id="flag_quest",
                title="Flag Quest",
                description="Set a flag.",
                stages=[
                    {
                        "id": "stage1",
                        "description": "Have the flag.",
                        "conditions": [{"type": "flag_set", "flag": "magic_flag"}],
                        "completion_flags": {},
                        "rewards": {},
                    }
                ],
            )
        )
        session.add(
            PlayerQuestProgress(
                player_id="p2",
                quest_id="flag_quest",
                current_stage_id="stage1",
                status="active",
                started_at=time.time(),
            )
        )
        session.commit()
        ctx = _ctx(session, player)

        QuestService().check_progression(Event(GameEvent.ITEM_TAKEN, {}), ctx)
        assert not any("completed" in m for m in ctx.messages)

        player.flags = {"magic_flag": True}
        QuestService().check_progression(Event(GameEvent.ITEM_TAKEN, {}), ctx)
        session.commit()

    assert any("completed" in m for m in ctx.messages)
