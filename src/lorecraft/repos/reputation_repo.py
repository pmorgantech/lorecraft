"""Reputation data access (Sprint 24.3)."""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.models.reputation import Reputation


class ReputationRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find(
        self, player_id: str, target_type: str, target_id: str
    ) -> Reputation | None:
        statement = select(Reputation).where(
            Reputation.player_id == player_id,
            Reputation.target_type == target_type,
            Reputation.target_id == target_id,
        )
        return self.session.exec(statement).first()

    def get_or_create(
        self, player_id: str, target_type: str, target_id: str
    ) -> Reputation:
        existing = self.find(player_id, target_type, target_id)
        if existing is not None:
            return existing
        created = Reputation(
            player_id=player_id, target_type=target_type, target_id=target_id
        )
        self.session.add(created)
        self.session.flush()
        return created

    def for_player(self, player_id: str) -> list[Reputation]:
        statement = (
            select(Reputation)
            .where(Reputation.player_id == player_id)
            .order_by(Reputation.target_type, Reputation.target_id)  # type: ignore[arg-type]
        )
        return list(self.session.exec(statement).all())
