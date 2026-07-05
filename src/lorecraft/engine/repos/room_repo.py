"""Room and world-state data access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, select

from lorecraft.models.world import Exit, Room, WorldClock, WorldMeta
from lorecraft.engine.repos.base import Repository


class RoomRepo(Repository[Room, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Room)

    def active(self, room_id: str) -> Room | None:
        room = self.get(room_id)
        if room is None or not room.is_active:
            return None
        return room

    def exits(self, room_id: str) -> Sequence[Exit]:
        statement = select(Exit).where(Exit.room_id == room_id)
        return self.session.exec(statement).all()

    def exit(self, room_id: str, direction: str) -> Exit | None:
        statement = select(Exit).where(
            Exit.room_id == room_id,
            Exit.direction == direction,
        )
        return self.session.exec(statement).first()

    def get_exits_with_names(
        self, room_id: str, visited: list[str] | None = None
    ) -> list[dict]:
        """Return exits enriched for UI (direction + dest name + known)."""
        exits = self.exits(room_id)
        result: list[dict] = []
        visited = visited or []
        for ex in exits:
            target = self.get(ex.target_room_id)
            result.append(
                {
                    "direction": ex.direction,
                    "target_room_id": ex.target_room_id,
                    "destination_name": target.name if target else ex.target_room_id,
                    "known": ex.target_room_id in visited if visited else True,
                    "locked": ex.locked,
                    "hidden": ex.hidden,
                }
            )
        return result

    def world_clock(self) -> WorldClock | None:
        return self.session.exec(select(WorldClock)).first()

    def world_meta(self) -> WorldMeta | None:
        return self.session.exec(select(WorldMeta)).first()
