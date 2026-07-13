"""Use-based skill improvement (Sprint 24.2).

Stateless per-call, mutating PlayerStats.skills — same session discipline
as every other Tier 2 service (never commits; caller's transaction owns
that). "Learn by doing": every use of a skill has a small chance to raise
its level, capped at MAX_LEVEL.
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.errors import NotFoundError
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.player import PlayerStats

MAX_LEVEL = 100
BASE_LEVEL = 0
IMPROVE_CHANCE = 0.1


class SkillService:
    def get_level(self, session: Session, player_id: str, skill_name: str) -> int:
        stats = session.get(PlayerStats, player_id)
        if stats is None:
            return BASE_LEVEL
        level = stats.discipline_ranks.get(skill_name)
        return int(level) if isinstance(level, (int, float)) else BASE_LEVEL

    def record_use(
        self,
        session: Session,
        rng: GameRng,
        player_id: str,
        skill_name: str,
    ) -> bool:
        """Roll a chance to improve `skill_name` by 1 level. Returns True if it did."""
        stats = session.get(PlayerStats, player_id)
        if stats is None:
            raise NotFoundError(
                f"No PlayerStats for player {player_id}", "not_found_player_stats"
            )

        current = self.get_level(session, player_id, skill_name)
        if current >= MAX_LEVEL:
            return False
        if not rng.chance(IMPROVE_CHANCE):
            return False

        stats.discipline_ranks = {**stats.discipline_ranks, skill_name: current + 1}
        session.add(stats)
        return True
