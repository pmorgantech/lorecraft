"""Quest and quest-progress data access."""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.features.quests.models import PlayerQuestProgress, Quest
from lorecraft.engine.repos.base import Repository


class QuestRepo(Repository[Quest, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Quest)

    def active_progress(self, player_id: str) -> list[PlayerQuestProgress]:
        return list(
            self.session.exec(
                select(PlayerQuestProgress)
                .where(PlayerQuestProgress.player_id == player_id)
                .where(PlayerQuestProgress.status == "active")
            ).all()
        )

    def all_active_progress(self) -> list[PlayerQuestProgress]:
        """Every player's active quest progress, for the scheduler-driven
        timeout sweep (QuestTimerService) which has no single player_id to
        scope to."""
        return list(
            self.session.exec(
                select(PlayerQuestProgress).where(
                    PlayerQuestProgress.status == "active"
                )
            ).all()
        )

    def all_progress(self, player_id: str) -> list[PlayerQuestProgress]:
        """Every quest-progress row for a player, any status (for the `score`
        report — Sprint 34.2), so completed and failed quests are counted too."""
        return list(
            self.session.exec(
                select(PlayerQuestProgress).where(
                    PlayerQuestProgress.player_id == player_id
                )
            ).all()
        )

    def player_progress(
        self, player_id: str, quest_id: str
    ) -> PlayerQuestProgress | None:
        return self.session.exec(
            select(PlayerQuestProgress)
            .where(PlayerQuestProgress.player_id == player_id)
            .where(PlayerQuestProgress.quest_id == quest_id)
        ).first()

    def add_progress(self, progress: PlayerQuestProgress) -> None:
        self.session.add(progress)
