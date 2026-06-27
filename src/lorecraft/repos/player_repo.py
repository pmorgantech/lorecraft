"""Player data access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, col, select

from lorecraft.models.player import Player, PlayerStats, SaveSlot
from lorecraft.models.session import PlayerSession
from lorecraft.repos.base import Repository


class PlayerRepo(Repository[Player, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Player)

    def by_username(self, username: str) -> Player | None:
        statement = select(Player).where(Player.username == username)
        return self.session.exec(statement).first()

    def stats(self, player_id: str) -> PlayerStats | None:
        return self.session.get(PlayerStats, player_id)

    def save_stats(self, stats: PlayerStats) -> PlayerStats:
        self.session.add(stats)
        return stats

    def active_session(self, player_id: str) -> PlayerSession | None:
        statement = (
            select(PlayerSession)
            .where(
                PlayerSession.player_id == player_id,
                PlayerSession.status == "active",
            )
            .order_by(col(PlayerSession.connected_at).desc())
        )
        return self.session.exec(statement).first()

    def save_slots(self, player_id: str) -> Sequence[SaveSlot]:
        statement = (
            select(SaveSlot)
            .where(SaveSlot.player_id == player_id)
            .order_by(col(SaveSlot.saved_at).desc())
        )
        return self.session.exec(statement).all()
