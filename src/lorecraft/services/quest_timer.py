"""Quest stage timeouts: timed clock-driven quest events (Sprint 30.2).

Engine-holding schedulable, same shape as RestockService: on every
TIME_ADVANCED tick, sweep every player's active quest progress and check
whether the current stage's `timeout_ticks` has elapsed since
`stage_started_epoch` (both in game-epoch units, like every other
scheduler-timed field in this engine). A timed-out stage applies its
`on_timeout` outcome -- move to a fallback `next_stage`, or fail the quest
if `next_stage` is null -- entirely data-driven from the quest's own YAML,
no per-quest special-casing.

Runs with no GameContext (a global sweep, not one player's command): reads/
writes Player.flags directly and narrates via ConnectionManager.send_to_player
(a no-op if that player isn't currently connected), the same pattern
services/transit.py uses for its own scheduler-driven narration.
"""

from __future__ import annotations

import asyncio
import time

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.models.player import Player
from lorecraft.models.quest import PlayerQuestProgress, Quest
from lorecraft.repos.quest_repo import QuestRepo
from lorecraft.types import JsonObject


def _stage_by_id(quest: Quest, stage_id: str) -> JsonObject | None:
    return next((s for s in quest.stages if s["id"] == stage_id), None)


class QuestTimerService:
    def __init__(self, game_engine: Engine, manager: ConnectionManager) -> None:
        self._game_engine = game_engine
        self._manager = manager
        self._bus: EventBus | None = None

    def register(self, bus: EventBus) -> None:
        self._bus = bus
        bus.on(GameEvent.TIME_ADVANCED, self._on_time_advanced)

    def _on_time_advanced(self, event: Event, ctx: object) -> None:
        del ctx
        current_epoch = float(event.payload.get("current_epoch", 0.0))  # type: ignore[arg-type]
        failed: list[str] = []

        with Session(self._game_engine) as session:
            repo = QuestRepo(session)
            for progress in repo.all_active_progress():
                self._check_one(session, repo, progress, current_epoch, failed)
            session.commit()

        if self._bus is None:
            return
        for player_id in failed:
            self._bus.emit(
                Event(GameEvent.QUEST_FAILED, {"player_id": player_id}), None
            )

    def _check_one(
        self,
        session: Session,
        repo: QuestRepo,
        progress: PlayerQuestProgress,
        current_epoch: float,
        failed: list[str],
    ) -> None:
        quest = repo.get(progress.quest_id)
        if quest is None:
            return
        stage = _stage_by_id(quest, progress.current_stage_id)
        if stage is None:
            return
        timeout_ticks = stage.get("timeout_ticks")
        if not isinstance(timeout_ticks, (int, float)):
            return
        started = progress.stage_started_epoch
        if started is None or current_epoch - started < timeout_ticks:
            return

        on_timeout = stage.get("on_timeout") or {}
        if not isinstance(on_timeout, dict):
            on_timeout = {}

        player = session.get(Player, progress.player_id)
        if player is not None:
            set_flags = on_timeout.get("set_flags") or {}
            if isinstance(set_flags, dict):
                player.flags = {**player.flags, **set_flags}
                session.add(player)

        message = str(on_timeout.get("message") or "")
        next_stage_id = on_timeout.get("next_stage")

        if isinstance(next_stage_id, str) and _stage_by_id(quest, next_stage_id):
            progress.current_stage_id = next_stage_id
            progress.stage_started_epoch = current_epoch
            status = "active"
        else:
            progress.status = "failed"
            progress.completed_at = time.time()
            failed.append(progress.player_id)
            status = "failed"
        session.add(progress)

        self._notify(progress.player_id, quest.title, progress, status, message)

    def _notify(
        self,
        player_id: str,
        quest_title: str,
        progress: PlayerQuestProgress,
        status: str,
        message: str,
    ) -> None:
        del quest_title, progress, status
        if message:
            self._send(
                player_id,
                {
                    "type": "feed_append",
                    "content": message,
                    "message_type": "room_event",
                },
            )
        # Per-player panel refresh (not a room broadcast): quest state is
        # private, so this targets exactly the one affected connection via
        # send_to_player, unlike game/broadcast.py's room-wide state_change.
        self._send(
            player_id,
            {"type": "state_change", "affected_panels": ["quest-tracker"]},
        )

    def _send(self, player_id: str, message: JsonObject) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no running event loop (e.g. in tests / scheduler-only contexts)
        asyncio.create_task(self._manager.send_to_player(player_id, message))
