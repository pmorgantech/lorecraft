"""Item data access."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlmodel import Session, select

from lorecraft.errors import ConflictError
from lorecraft.models.world import Item, RoomItem
from lorecraft.repos.base import Repository

log = logging.getLogger(__name__)


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
        q_words = _query_words(query)
        exact: list[tuple[RoomItem, Item]] = []
        fuzzy: list[tuple[RoomItem, Item]] = []
        for room_item, item in self.items_in_room(room_id):
            if _item_matches_query(q, q_words, item):
                exact.append((room_item, item))
            elif _item_matches_words(q_words, item):
                fuzzy.append((room_item, item))
        return exact if exact else fuzzy

    def search_player_items(self, item_ids: Sequence[str], query: str) -> list[Item]:
        """Return all player inventory items matching query, deduplicated by item id.
        Exact matches are returned first; if none, falls back to word-subset fuzzy matches."""
        q = _normalize_item_name(query)
        q_words = _query_words(query)
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
            if _item_matches_query(q, q_words, item):
                exact.append(item)
            elif _item_matches_words(q_words, item):
                fuzzy.append(item)
        return exact if exact else fuzzy

    def inventory_slots_matching(
        self, item_ids: Sequence[str], query: str
    ) -> list[tuple[int, Item]]:
        """Return inventory indices and items for every carried slot matching query."""
        q = _normalize_item_name(query)
        q_words = _query_words(query)
        slots: list[tuple[int, Item]] = []
        for index, item_id in enumerate(item_ids):
            item = self.get(item_id)
            if item is None:
                continue
            if _item_matches_query(q, q_words, item) or _item_matches_words(
                q_words, item
            ):
                slots.append((index, item))
        return slots

    def expanded_room_instances(
        self, room_id: str, query: str
    ) -> list[tuple[RoomItem, Item]]:
        """Expand room stacks into one entry per carried instance for indexed take."""
        instances: list[tuple[RoomItem, Item]] = []
        for room_item, item in self.search_in_room(room_id, query):
            instances.extend((room_item, item) for _ in range(room_item.quantity))
        return instances

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
        if quantity > room_item.quantity:
            log.error(
                "item_quantity_underflow: item_id=%s room_id=%s requested=%d available=%d",
                room_item.item_id,
                room_item.room_id,
                quantity,
                room_item.quantity,
            )
            raise ConflictError(
                f"Attempted to remove {quantity} but only {room_item.quantity} available",
                "conflict_quantity_underflow",
            )
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


def _singularize_word(word: str) -> str:
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _query_words(query: str) -> frozenset[str]:
    words = _normalize_item_name(query).split()
    return frozenset(_singularize_word(word) for word in words)


def _item_name_words(item: Item) -> frozenset[str]:
    words = _normalize_item_name(item.name).split()
    return frozenset(_singularize_word(word) for word in words)


def _item_alias_word_sets(item: Item) -> list[frozenset[str]]:
    return [
        frozenset(
            _singularize_word(word) for word in _normalize_item_name(alias).split()
        )
        for alias in item.aliases
    ]


def _item_matches_query(q: str, q_words: frozenset[str], item: Item) -> bool:
    n = _normalize_item_name(item.name)
    i = _normalize_item_name(item.id)
    if q in {n, i}:
        return True
    aliases = {_normalize_item_name(alias) for alias in item.aliases}
    return q in aliases


def _item_matches_words(q_words: frozenset[str], item: Item) -> bool:
    if _words_match(q_words, _item_name_words(item)):
        return True
    return any(
        _words_match(q_words, alias_words)
        for alias_words in _item_alias_word_sets(item)
    )


def _words_match(query_words: frozenset[str], name_words: frozenset[str]) -> bool:
    """Return True if every word in the query appears in the item name."""
    return bool(query_words) and query_words.issubset(name_words)
