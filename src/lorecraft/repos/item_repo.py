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

    def items_in_room(self, room_id: str) -> Sequence[tuple[RoomItem, Item]]:
        items: list[tuple[RoomItem, Item]] = []
        for room_item in self.room_items(room_id):
            item = self.get(room_item.item_id)
            if item is not None:
                items.append((room_item, item))
        return items

    def find_in_room(
        self, room_id: str, name_or_id: str
    ) -> tuple[RoomItem, Item] | None:
        normalized = _normalize_item_name(name_or_id)
        for room_item, item in self.items_in_room(room_id):
            if normalized in {
                _normalize_item_name(item.id),
                _normalize_item_name(item.name),
            }:
                return room_item, item
        return None

    def find_player_item(self, item_ids: Sequence[str], name_or_id: str) -> Item | None:
        normalized = _normalize_item_name(name_or_id)
        for item_id in item_ids:
            item = self.get(item_id)
            if item is None:
                continue
            if normalized in {
                _normalize_item_name(item.id),
                _normalize_item_name(item.name),
            }:
                return item
        return None

    def add_to_room(self, room_item: RoomItem) -> RoomItem:
        self.session.add(room_item)
        return room_item

    def remove_from_room(self, room_item: RoomItem, quantity: int = 1) -> None:
        room_item.quantity -= quantity
        if room_item.quantity <= 0:
            self.session.delete(room_item)

    def increment_room_item(
        self, room_id: str, item_id: str, quantity: int = 1
    ) -> RoomItem:
        statement = select(RoomItem).where(
            RoomItem.room_id == room_id,
            RoomItem.item_id == item_id,
        )
        room_item = self.session.exec(statement).first()
        if room_item is None:
            room_item = RoomItem(room_id=room_id, item_id=item_id, quantity=quantity)
            self.session.add(room_item)
            return room_item

        room_item.quantity += quantity
        return room_item


def _normalize_item_name(value: str) -> str:
    return " ".join(value.casefold().split())
