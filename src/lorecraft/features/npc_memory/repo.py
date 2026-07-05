"""NPC memory data access (Sprint 30.1)."""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.features.npc_memory.models import NpcMemory
from lorecraft.types import JsonScalar


class NpcMemoryRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find(self, player_id: str, npc_id: str, key: str) -> NpcMemory | None:
        statement = select(NpcMemory).where(
            NpcMemory.player_id == player_id,
            NpcMemory.npc_id == npc_id,
            NpcMemory.key == key,
        )
        return self.session.exec(statement).first()

    def remembers(self, player_id: str, npc_id: str, key: str) -> bool:
        memory = self.find(player_id, npc_id, key)
        return memory is not None and bool(memory.value)

    def set(
        self, player_id: str, npc_id: str, key: str, value: JsonScalar = True
    ) -> NpcMemory:
        existing = self.find(player_id, npc_id, key)
        if existing is not None:
            existing.value = value
            self.session.add(existing)
            return existing
        created = NpcMemory(player_id=player_id, npc_id=npc_id, key=key, value=value)
        self.session.add(created)
        self.session.flush()
        return created

    def all_for(self, player_id: str, npc_id: str) -> list[NpcMemory]:
        statement = select(NpcMemory).where(
            NpcMemory.player_id == player_id, NpcMemory.npc_id == npc_id
        )
        return list(self.session.exec(statement).all())
