"""Tests for Sprint 30.1: quest stage `branches` (conditions + next_stage +
side_effects) and the `adjust_reputation` side effect consequence."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player
from lorecraft.features.quests.models import Quest
from lorecraft.engine.models.world import Room, WorldClock
from lorecraft.npc.dialogue import _start_quest
from lorecraft.repos.dialogue_repo import DialogueRepo
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.features.quests.repo import QuestRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.reputation.conditions import register as _register_reputation
from lorecraft.features.quests.service import QuestService
from lorecraft.features.reputation.service import ReputationService

# The `adjust_reputation` side effect used to register as an import side effect;
# it now registers via the reputation feature's register(). Call it once here.
_register_reputation()


def _engine():
    e = create_engine("sqlite://")
    create_tables(game_engine=e, audit_engine=create_engine("sqlite://"))
    return e


def _seed_rooms(session: Session) -> None:
    session.add(Room(id="square", name="Square", description="d.", map_x=0, map_y=0))
    session.add(Room(id="docks", name="Docks", description="d.", map_x=1, map_y=0))
    session.add(Room(id="cave", name="Cave", description="d.", map_x=2, map_y=0))
    session.add(WorldClock(game_epoch=0.0, real_epoch=0.0))


def _player(visited_rooms: list[str] | None = None) -> Player:
    return Player(
        id="p1",
        username="hero",
        current_room_id="square",
        respawn_room_id="square",
        visited_rooms=visited_rooms or ["square"],
    )


def _ctx(session: Session, player: Player) -> GameContext:
    room = session.get(Room, player.current_room_id)
    assert room is not None
    return GameContext(
        player=player,
        room=room,
        clock=session.get(WorldClock, 1),
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


def _branching_quest() -> Quest:
    return Quest(
        id="rescue",
        title="Rescue the Merchant",
        description="A merchant needs help.",
        stages=[
            {
                "id": "start",
                "description": "Decide how to help.",
                "conditions": [{"type": "flag_set", "flag": "ready"}],
                "branches": [
                    {
                        "conditions": [{"type": "room_visited", "room_id": "docks"}],
                        "next_stage": "paid_route",
                        "side_effects": {
                            "set_flags": ["took_docks_route"],
                            "adjust_reputation": {
                                "target_type": "npc",
                                "target_id": "merchant",
                                "delta": 10,
                            },
                        },
                    },
                    {
                        "conditions": [{"type": "room_visited", "room_id": "cave"}],
                        "next_stage": "risky_route",
                        "side_effects": {
                            "set_flags": ["took_cave_route"],
                            "adjust_reputation": {
                                "target_type": "npc",
                                "target_id": "merchant",
                                "delta": -5,
                            },
                        },
                    },
                ],
            },
            {
                "id": "paid_route",
                "description": "You took the safe way.",
                "conditions": [],
                "rewards": {"xp": 10},
                "terminal": True,
            },
            {
                "id": "risky_route",
                "description": "You took the dangerous shortcut.",
                "conditions": [],
                "rewards": {"xp": 20},
                "terminal": True,
            },
        ],
    )


def _seed_branching_quest(session: Session, *, visited_rooms: list[str]) -> Player:
    _seed_rooms(session)
    session.add(_branching_quest())
    player = _player(visited_rooms=visited_rooms)
    session.add(player)
    return player


class TestQuestBranching:
    def test_no_branch_condition_met_stalls(self) -> None:
        e = _engine()
        with Session(e) as session:
            player = _seed_branching_quest(session, visited_rooms=["square"])
            session.commit()
            ctx = _ctx(session, player)
            _start_quest("rescue", ctx)
            player.flags = {"ready": True}
            session.commit()

            QuestService().check_progression(Event(GameEvent.PLAYER_MOVED, {}), ctx)
            session.commit()

            progress = ctx.quest_repo.player_progress("p1", "rescue")

        assert progress is not None
        assert progress.current_stage_id == "start"

    def test_docks_branch_selected_and_side_effects_applied(self) -> None:
        e = _engine()
        with Session(e) as session:
            player = _seed_branching_quest(session, visited_rooms=["square", "docks"])
            session.commit()
            ctx = _ctx(session, player)
            _start_quest("rescue", ctx)
            player.flags = {**player.flags, "ready": True}
            session.commit()

            QuestService().check_progression(Event(GameEvent.PLAYER_MOVED, {}), ctx)
            session.commit()

            progress = ctx.quest_repo.player_progress("p1", "rescue")
            standing = ReputationService().standing_of(session, "p1", "npc", "merchant")
            flags = dict(player.flags)

        assert progress is not None
        assert progress.current_stage_id == "paid_route"
        assert flags.get("took_docks_route") is True
        assert standing == 10

    def test_cave_branch_selected_when_docks_not_visited(self) -> None:
        e = _engine()
        with Session(e) as session:
            player = _seed_branching_quest(session, visited_rooms=["square", "cave"])
            session.commit()
            ctx = _ctx(session, player)
            _start_quest("rescue", ctx)
            player.flags = {**player.flags, "ready": True}
            session.commit()

            QuestService().check_progression(Event(GameEvent.PLAYER_MOVED, {}), ctx)
            session.commit()

            progress = ctx.quest_repo.player_progress("p1", "rescue")
            standing = ReputationService().standing_of(session, "p1", "npc", "merchant")
            flags = dict(player.flags)

        assert progress is not None
        assert progress.current_stage_id == "risky_route"
        assert flags.get("took_cave_route") is True
        assert standing == -5

    def test_first_matching_branch_wins_when_both_conditions_met(self) -> None:
        e = _engine()
        with Session(e) as session:
            player = _seed_branching_quest(
                session, visited_rooms=["square", "docks", "cave"]
            )
            session.commit()
            ctx = _ctx(session, player)
            _start_quest("rescue", ctx)
            player.flags = {**player.flags, "ready": True}
            session.commit()

            QuestService().check_progression(Event(GameEvent.PLAYER_MOVED, {}), ctx)
            session.commit()

            progress = ctx.quest_repo.player_progress("p1", "rescue")

        assert progress is not None
        assert progress.current_stage_id == "paid_route"  # docks branch listed first

    def test_completing_final_stage_still_awards_legacy_rewards(self) -> None:
        e = _engine()
        with Session(e) as session:
            player = _seed_branching_quest(session, visited_rooms=["square", "docks"])
            session.commit()
            ctx = _ctx(session, player)
            _start_quest("rescue", ctx)
            player.flags = {**player.flags, "ready": True}
            session.commit()

            QuestService().check_progression(Event(GameEvent.PLAYER_MOVED, {}), ctx)
            session.commit()
            ctx.messages.clear()

            QuestService().check_progression(Event(GameEvent.PLAYER_MOVED, {}), ctx)
            session.commit()

            progress = ctx.quest_repo.player_progress("p1", "rescue")

        assert progress is not None
        assert progress.status == "completed"
        assert any("gain 10 experience" in m for m in ctx.messages)

    def test_stage_started_epoch_stamped_on_transition(self) -> None:
        e = _engine()
        with Session(e) as session:
            player = _seed_branching_quest(session, visited_rooms=["square", "docks"])
            session.commit()
            ctx = _ctx(session, player)
            clock = session.get(WorldClock, 1)
            assert clock is not None
            clock.game_epoch = 100.0
            session.add(clock)
            session.commit()

            _start_quest("rescue", ctx)
            session.commit()
            progress = ctx.quest_repo.player_progress("p1", "rescue")
            assert progress is not None
            assert progress.stage_started_epoch == 100.0

            player.flags = {**player.flags, "ready": True}
            clock.game_epoch = 150.0
            session.add(clock)
            session.commit()

            QuestService().check_progression(Event(GameEvent.PLAYER_MOVED, {}), ctx)
            session.commit()
            progress = ctx.quest_repo.player_progress("p1", "rescue")

        assert progress is not None
        assert progress.stage_started_epoch == 150.0
