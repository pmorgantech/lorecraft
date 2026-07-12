"""Player data access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, col, select

from lorecraft.engine.models.player import Player, PlayerStats, SaveSlot
from lorecraft.engine.models.player_auth import PlayerAuth
from lorecraft.engine.models.session import PlayerSession
from lorecraft.engine.repos.base import Repository


class PlayerRepo(Repository[Player, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Player)

    def by_username(self, username: str) -> Player | None:
        statement = select(Player).where(Player.username == username)
        return self.session.exec(statement).first()

    def stats(self, player_id: str) -> PlayerStats:
        """Return the player's stats row, lazily creating it on first access.

        Every real player is entitled to exactly one PlayerStats row, but no
        creation path writes one eagerly -- character creation, the dev/seed
        helpers, and save-load all leave it absent (an empty stats snapshot
        round-trips to another empty snapshot). This get-or-create is the single
        point that guarantees the row exists, so downstream reward/XP grants,
        which are gated on "stats present", always have somewhere to land. The
        row uses the model's own defaults (level 1, 0 xp, base stats) -- engine
        defaults, not any feature's balance policy, so this stays Tier 1
        mechanism. Existing players missing the row are auto-healed on first
        read; the staged row persists with the surrounding unit of work.
        """
        existing = self.session.get(PlayerStats, player_id)
        if existing is not None:
            return existing
        created = PlayerStats(player_id=player_id)
        self.session.add(created)
        return created

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

    def list_all(
        self, *, offset: int = 0, limit: int | None = None
    ) -> Sequence[Player]:
        statement = select(Player).order_by(col(Player.username)).offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return self.session.exec(statement).all()

    def latest_session(self, player_id: str) -> PlayerSession | None:
        statement = (
            select(PlayerSession)
            .where(PlayerSession.player_id == player_id)
            .order_by(col(PlayerSession.connected_at).desc())
        )
        return self.session.exec(statement).first()

    def in_room(self, room_id: str) -> Sequence[Player]:
        statement = (
            select(Player)
            .where(Player.current_room_id == room_id)
            .order_by(col(Player.username))
        )
        return self.session.exec(statement).all()

    def auth_for_player(self, player_id: str) -> PlayerAuth | None:
        statement = select(PlayerAuth).where(PlayerAuth.player_id == player_id)
        return self.session.exec(statement).first()

    def auth_by_subject(
        self, provider: str, provider_subject: str
    ) -> PlayerAuth | None:
        statement = select(PlayerAuth).where(
            PlayerAuth.provider == provider,
            PlayerAuth.provider_subject == provider_subject,
        )
        return self.session.exec(statement).first()

    def add_auth(self, player_auth: PlayerAuth) -> PlayerAuth:
        self.session.add(player_auth)
        return player_auth
