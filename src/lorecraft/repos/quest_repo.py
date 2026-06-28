"""Quest and quest-progress data access."""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.models.quest import PlayerQuestProgress, Quest
from lorecraft.repos.base import Repository


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
