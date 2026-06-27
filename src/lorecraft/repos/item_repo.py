"""Item data access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, select

from lorecraft.models.world import Item, RoomItem
from lorecraft.repos.base import Repository


class ItemRepo(Repository[Item, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Item)

    def room_items(self, room_id: str) -> Sequence[RoomItem]:
        statement = select(RoomItem).where(RoomItem.room_id == room_id)
        return self.session.exec(statement).all()

    def add_to_room(self, room_item: RoomItem) -> RoomItem:
        self.session.add(room_item)
        return room_item
