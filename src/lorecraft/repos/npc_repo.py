"""NPC data access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, select

from lorecraft.models.world import NPC
from lorecraft.repos.base import Repository


class NpcRepo(Repository[NPC, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, NPC)

    def in_room(self, room_id: str) -> Sequence[NPC]:
        statement = select(NPC).where(NPC.current_room_id == room_id)
        return self.session.exec(statement).all()
