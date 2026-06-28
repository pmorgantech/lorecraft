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

    def search_in_room(self, room_id: str, query: str) -> list[tuple[RoomItem, Item]]:
        """Return all room items that match query. Exact matches are returned first;
        if none, falls back to word-subset fuzzy matches."""
        q = _normalize_item_name(query)
        q_words = frozenset(q.split())
        exact: list[tuple[RoomItem, Item]] = []
        fuzzy: list[tuple[RoomItem, Item]] = []
        for room_item, item in self.items_in_room(room_id):
            n = _normalize_item_name(item.name)
            i = _normalize_item_name(item.id)
            if q in {n, i}:
                exact.append((room_item, item))
            elif _words_match(q_words, frozenset(n.split())):
                fuzzy.append((room_item, item))
        return exact if exact else fuzzy

    def search_player_items(self, item_ids: Sequence[str], query: str) -> list[Item]:
        """Return all player inventory items matching query, deduplicated by item id.
        Exact matches are returned first; if none, falls back to word-subset fuzzy matches."""
        q = _normalize_item_name(query)
        q_words = frozenset(q.split())
        exact: list[Item] = []
        fuzzy: list[Item] = []
        seen: set[str] = set()
        for item_id in item_ids:
            if item_id in seen:
                continue
            item = self.get(item_id)
            if item is None:
                continue
            seen.add(item_id)
            n = _normalize_item_name(item.name)
            i = _normalize_item_name(item.id)
            if q in {n, i}:
                exact.append(item)
            elif _words_match(q_words, frozenset(n.split())):
                fuzzy.append(item)
        return exact if exact else fuzzy

    def find_in_room(
        self, room_id: str, name_or_id: str
    ) -> tuple[RoomItem, Item] | None:
        results = self.search_in_room(room_id, name_or_id)
        return results[0] if results else None

    def find_player_item(self, item_ids: Sequence[str], name_or_id: str) -> Item | None:
        results = self.search_player_items(item_ids, name_or_id)
        return results[0] if results else None

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


def _words_match(query_words: frozenset[str], name_words: frozenset[str]) -> bool:
    """Return True if every word in the query appears in the item name."""
    return bool(query_words) and query_words.issubset(name_words)
