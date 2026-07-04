"""Tests for Sprint 30.2: QuestTimerService (timed clock-driven quest
events) -- a stage's `timeout_ticks`/`on_timeout` sweep, driven by
TIME_ADVANCED, independent of any player command."""

from __future__ import annotations

from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.events import Event, EventBus, GameEvent
from lorecraft.models.player import Player
from lorecraft.models.quest import PlayerQuestProgress, Quest
from lorecraft.services.quest_timer import QuestTimerService


def _engine():
    e = create_engine("sqlite://")
    create_tables(game_engine=e, audit_engine=create_engine("sqlite://"))
    return e


def _seed(
    session: Session,
    *,
    stage_started_epoch: float = 0.0,
    current_stage_id: str = "wait",
) -> None:
    session.add(
        Quest(
            id="caravan",
            title="Catch the Caravan",
            description="Board before it leaves.",
            stages=[
                {
                    "id": "wait",
                    "description": "Get to the depot before it leaves.",
                    "conditions": [{"type": "flag_set", "flag": "boarded"}],
                    "timeout_ticks": 50,
                    "on_timeout": {
                        "next_stage": "missed",
                        "message": "The caravan leaves without you.",
                        "set_flags": {"missed_caravan": True},
                    },
                },
                {
                    "id": "missed",
                    "description": "You'll have to catch the next one.",
                    "conditions": [],
                    "terminal": True,
                },
            ],
        )
    )
    session.add(
        Player(id="p1", username="hero", current_room_id="sq", respawn_room_id="sq")
    )
    session.add(
        PlayerQuestProgress(
            player_id="p1",
            quest_id="caravan",
            current_stage_id=current_stage_id,
            status="active",
            started_at=0.0,
            stage_started_epoch=stage_started_epoch,
        )
    )


def _seed_no_fallback(session: Session, *, stage_started_epoch: float = 0.0) -> None:
    session.add(
        Quest(
            id="delivery",
            title="Deliver the Package",
            description="Deliver it in time.",
            stages=[
                {
                    "id": "deliver",
                    "description": "Deliver before time runs out.",
                    "conditions": [{"type": "flag_set", "flag": "delivered"}],
                    "timeout_ticks": 20,
                    "on_timeout": {"message": "Too late -- the package spoiled."},
                }
            ],
        )
    )
    session.add(
        Player(id="p2", username="courier", current_room_id="sq", respawn_room_id="sq")
    )
    session.add(
        PlayerQuestProgress(
            player_id="p2",
            quest_id="delivery",
            current_stage_id="deliver",
            status="active",
            started_at=0.0,
            stage_started_epoch=stage_started_epoch,
        )
    )


class TestQuestTimeout:
    def test_not_yet_elapsed_leaves_stage_untouched(self) -> None:
        e = _engine()
        with Session(e) as session:
            _seed(session, stage_started_epoch=0.0)
            session.commit()

            service = QuestTimerService(e, ConnectionManager())
            service._on_time_advanced(
                Event(GameEvent.TIME_ADVANCED, {"current_epoch": 30.0}), None
            )

            progress = session.exec(
                select(PlayerQuestProgress).where(PlayerQuestProgress.player_id == "p1")
            ).first()

        assert progress is not None
        assert progress.current_stage_id == "wait"
        assert progress.status == "active"

    def test_elapsed_advances_to_fallback_stage_and_sets_flags(self) -> None:
        e = _engine()
        with Session(e) as session:
            _seed(session, stage_started_epoch=0.0)
            session.commit()

        service = QuestTimerService(e, ConnectionManager())
        service._on_time_advanced(
            Event(GameEvent.TIME_ADVANCED, {"current_epoch": 60.0}), None
        )

        with Session(e) as session:
            progress = session.exec(
                select(PlayerQuestProgress).where(PlayerQuestProgress.player_id == "p1")
            ).first()
            player = session.get(Player, "p1")

        assert progress is not None
        assert progress.current_stage_id == "missed"
        assert progress.status == "active"
        assert progress.stage_started_epoch == 60.0
        assert player is not None
        assert player.flags.get("missed_caravan") is True

    def test_elapsed_with_no_fallback_fails_quest_and_emits_event(self) -> None:
        e = _engine()
        with Session(e) as session:
            _seed_no_fallback(session, stage_started_epoch=0.0)
            session.commit()

        bus = EventBus()
        failed_payloads: list[dict[str, object]] = []
        bus.on(
            GameEvent.QUEST_FAILED,
            lambda event, _ctx: failed_payloads.append(dict(event.payload)),
        )
        service = QuestTimerService(e, ConnectionManager())
        service.register(bus)

        bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 25.0}), None)

        with Session(e) as session:
            progress = session.exec(
                select(PlayerQuestProgress).where(PlayerQuestProgress.player_id == "p2")
            ).first()

        assert progress is not None
        assert progress.status == "failed"
        assert progress.completed_at is not None
        assert failed_payloads == [{"player_id": "p2"}]

    def test_stage_without_timeout_ticks_is_never_touched(self) -> None:
        e = _engine()
        with Session(e) as session:
            session.add(
                Quest(
                    id="open_ended",
                    title="Open-Ended Quest",
                    description="No deadline.",
                    stages=[
                        {
                            "id": "only",
                            "description": "Do it whenever.",
                            "conditions": [{"type": "flag_set", "flag": "done"}],
                        }
                    ],
                )
            )
            session.add(
                Player(
                    id="p3",
                    username="idler",
                    current_room_id="sq",
                    respawn_room_id="sq",
                )
            )
            session.add(
                PlayerQuestProgress(
                    player_id="p3",
                    quest_id="open_ended",
                    current_stage_id="only",
                    status="active",
                    started_at=0.0,
                    stage_started_epoch=0.0,
                )
            )
            session.commit()

        service = QuestTimerService(e, ConnectionManager())
        service._on_time_advanced(
            Event(GameEvent.TIME_ADVANCED, {"current_epoch": 1_000_000.0}), None
        )

        with Session(e) as session:
            progress = session.exec(
                select(PlayerQuestProgress).where(PlayerQuestProgress.player_id == "p3")
            ).first()

        assert progress is not None
        assert progress.status == "active"
        assert progress.current_stage_id == "only"
