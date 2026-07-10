"""NPC data access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, select

from lorecraft.engine.models.world import NPC
from lorecraft.engine.repos.base import Repository


class NpcRepo(Repository[NPC, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, NPC)

    def in_room(self, room_id: str) -> Sequence[NPC]:
        statement = select(NPC).where(NPC.current_room_id == room_id)
        return self.session.exec(statement).all()

    def find_in_room(self, room_id: str, name_or_id: str) -> NPC | None:
        query = name_or_id.strip().lower()
        return next(
            (
                npc
                for npc in self.in_room(room_id)
                if npc.name.lower().startswith(query)
            ),
            None,
        )

    def escorting(self, player_id: str) -> Sequence[NPC]:
        """NPCs currently following `player_id` (Sprint 68 escort quests)."""
        statement = select(NPC).where(NPC.following_player_id == player_id)
        return self.session.exec(statement).all()
