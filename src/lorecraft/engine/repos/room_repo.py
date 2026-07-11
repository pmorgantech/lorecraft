"""Room and world-state data access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, select

from lorecraft.engine.models.world import Exit, Room, WorldClock, WorldMeta
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

    def rooms_in_area(self, area_id: str) -> Sequence[Room]:
        """All rooms in a zone (scripting engine A5: weather fronts, zone narration)."""
        return self.session.exec(select(Room).where(Room.area_id == area_id)).all()

    def resolve_ref(self, ref: str) -> Room | None:
        """Resolve a human-typed room reference to a room, or ``None`` if not unique.

        Accepts, in order: an exact room **id** (`inner_vault`); a zone-qualified
        `zone.room` where the tail is an id or a name (`town.inner_vault`,
        `town.The Inner Vault`); or a bare **name**, case-insensitive
        (`The Inner Vault`). A bare name matching more than one room (or a
        `zone.name` matching none) returns ``None`` so the caller can report it —
        there are no integer room ids, so zone-qualifying is how you disambiguate
        rooms that share a name.
        """
        ref = ref.strip()
        if not ref:
            return None
        exact = self.get(ref)
        if exact is not None:
            return exact

        zone: str | None = None
        tail = ref
        if "." in ref:
            zone, tail = (part.strip() for part in ref.split(".", 1))
            zoned_by_id = self.get(tail)
            if zoned_by_id is not None and zoned_by_id.area_id == zone:
                return zoned_by_id

        folded = tail.casefold()
        matches = [
            room
            for room in self.session.exec(select(Room)).all()
            if room.name.casefold() == folded and (zone is None or room.area_id == zone)
        ]
        return matches[0] if len(matches) == 1 else None

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
