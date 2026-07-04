"""Reputation/standing service (Sprint 24.3).

Stateless per-call, same shape as ItemLocationService/LedgerService: methods
take the caller's Session and never commit/rollback themselves.
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.repos.reputation_repo import ReputationRepo

MIN_STANDING = -100
MAX_STANDING = 100


class ReputationService:
    def standing_of(
        self, session: Session, player_id: str, target_type: str, target_id: str
    ) -> int:
        repo = ReputationRepo(session)
        existing = repo.find(player_id, target_type, target_id)
        return existing.standing if existing is not None else 0

    def adjust(
        self,
        session: Session,
        player_id: str,
        target_type: str,
        target_id: str,
        delta: int,
    ) -> int:
        repo = ReputationRepo(session)
        reputation = repo.get_or_create(player_id, target_type, target_id)
        reputation.standing = max(
            MIN_STANDING, min(MAX_STANDING, reputation.standing + delta)
        )
        session.add(reputation)
        return reputation.standing
