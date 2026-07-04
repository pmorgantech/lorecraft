"""Innate trait grant/revoke service (Sprint 24.1).

Stateless per-call: mutates PlayerStats.traits, the list InnateTraitSource
(game/standard_traits.py) reads. Never commits — caller's transaction owns
that, matching every other Tier 2 service's session discipline.
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.errors import NotFoundError
from lorecraft.models.player import PlayerStats


class TraitService:
    def grant(self, session: Session, player_id: str, trait_name: str) -> None:
        stats = session.get(PlayerStats, player_id)
        if stats is None:
            raise NotFoundError(
                f"No PlayerStats for player {player_id}", "not_found_player_stats"
            )
        if trait_name not in stats.traits:
            stats.traits = [*stats.traits, trait_name]
            session.add(stats)

    def revoke(self, session: Session, player_id: str, trait_name: str) -> None:
        stats = session.get(PlayerStats, player_id)
        if stats is None:
            raise NotFoundError(
                f"No PlayerStats for player {player_id}", "not_found_player_stats"
            )
        if trait_name in stats.traits:
            stats.traits = [name for name in stats.traits if name != trait_name]
            session.add(stats)

    def has(self, session: Session, player_id: str, trait_name: str) -> bool:
        stats = session.get(PlayerStats, player_id)
        return stats is not None and trait_name in stats.traits
