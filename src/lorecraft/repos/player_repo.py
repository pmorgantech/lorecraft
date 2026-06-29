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

    def player_session(self, session_id: str) -> PlayerSession | None:
        return self.session.get(PlayerSession, session_id)

    def reconnectable_session(self, player_id: str, now: float) -> PlayerSession | None:
        statement = (
            select(PlayerSession)
            .where(
                PlayerSession.player_id == player_id,
                PlayerSession.status == "grace",
                col(PlayerSession.grace_expires_at).is_not(None),
                col(PlayerSession.grace_expires_at) > now,
            )
            .order_by(col(PlayerSession.disconnected_at).desc())
        )
        return self.session.exec(statement).first()

    def expired_grace_sessions(
        self, now: float, *, player_id: str | None = None
    ) -> Sequence[PlayerSession]:
        statement = select(PlayerSession).where(
            PlayerSession.status == "grace",
            col(PlayerSession.grace_expires_at).is_not(None),
            col(PlayerSession.grace_expires_at) <= now,
        )
        if player_id is not None:
            statement = statement.where(PlayerSession.player_id == player_id)
        return self.session.exec(statement).all()

    def add_session(self, player_session: PlayerSession) -> PlayerSession:
        self.session.add(player_session)
        return player_session

    def save_slots(self, player_id: str) -> Sequence[SaveSlot]:
        statement = (
            select(SaveSlot)
            .where(SaveSlot.player_id == player_id)
            .order_by(col(SaveSlot.saved_at).desc())
        )
        return self.session.exec(statement).all()

    def save_slot(self, player_id: str, slot_name: str) -> SaveSlot | None:
        statement = select(SaveSlot).where(
            SaveSlot.player_id == player_id,
            SaveSlot.slot_name == slot_name,
        )
        return self.session.exec(statement).first()

    def add_save_slot(self, save_slot: SaveSlot) -> SaveSlot:
        self.session.add(save_slot)
        return save_slot

    def list_all(self, limit: int = 50) -> Sequence[Player]:
        statement = select(Player).order_by(col(Player.username)).limit(limit)
        return self.session.exec(statement).all()
