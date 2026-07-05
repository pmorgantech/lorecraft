"""Item data access: definition lookup and the word-matching engine.

Location-aware queries (what's in a room, what a player carries) are backed
by ItemStack (models/items.py) via StackRepo, replacing the old RoomItem
table and Player.inventory list (Sprint 16, engine_core.md §3.2).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypeVar

from sqlmodel import Session, col, select

from lorecraft.engine.game.holders import Location
from lorecraft.engine.models.items import ItemStack
from lorecraft.engine.models.world import Item
from lorecraft.engine.repos.base import Repository
from lorecraft.engine.repos.stack_repo import StackRepo

_C = TypeVar("_C")


class ItemRepo(Repository[Item, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Item)
        self._stacks = StackRepo(session)

    def get_many(self, ids: Iterable[str]) -> dict[str, Item]:
        """Batch-load full Item rows by id in a single query, keyed by id.

        Ids with no matching row are simply absent from the result; duplicate
        ids are collapsed. An empty id set short-circuits without a query. Used
        to eliminate per-stack N+1 round-trips (see _pair_with_items) for callers
        that need the whole definition (take/drop/use). Parser noun-resolution,
        which only needs name+aliases, uses the lighter name_index projection.
        """
        unique = list(dict.fromkeys(ids))
        if not unique:
            return {}
        statement = select(Item).where(col(Item.id).in_(unique))
        return {item.id: item for item in self.session.exec(statement).all()}

    def name_index(self, ids: Iterable[str]) -> dict[str, tuple[str, list[str]]]:
        """Project ``(name, aliases)`` for the given item ids, keyed by id.

        A column projection for the parser-resolution hot path: it selects only
        the three fields noun-matching needs, so — unlike get_many — it neither
        builds full Item ORM instances nor decodes the unused JSON columns
        (``usable_with``/``loot_table``/``effects``). Profiling the Sprint 36.1
        result showed that full-row materialization, not the matcher scan, was
        the residual parse cost at large inventory sizes (roadmap Sprint 36.2).

        Ids with no row are absent; duplicate ids collapse; empty input skips
        the query. Each aliases list is copied so callers can't mutate cached
        column state.
        """
        unique = list(dict.fromkeys(ids))
        if not unique:
            return {}
        statement = select(Item.id, Item.name, Item.aliases).where(
            col(Item.id).in_(unique)
        )
        return {
            row_id: (name, list(aliases))
            for row_id, name, aliases in self.session.exec(statement).all()
        }

    def items_in_room(self, room_id: str) -> list[tuple[ItemStack, Item]]:
        """All stacks loose in a room, paired with their Item definition."""
        stacks = self._stacks.stacks_at(Location("room", room_id))
        return self._pair_with_items(stacks)

    def search_in_room(self, room_id: str, query: str) -> list[tuple[ItemStack, Item]]:
        """Return all room stacks that match query. Exact matches are returned first;
        if none, falls back to word-subset fuzzy matches."""
        return _best_matches(query, self.items_in_room(room_id))

    def stacks_carried_by(self, player_id: str) -> list[tuple[ItemStack, Item]]:
        """Every stack a player carries loose (slot=None), paired with its Item."""
        stacks = self._stacks.stacks_at(Location("player", player_id))
        return self._pair_with_items(stacks)

    def search_player_items(self, player_id: str, query: str) -> list[Item]:
        """Return all carried items matching query, deduplicated by item id.
        Exact matches are returned first; if none, falls back to word-subset fuzzy matches."""
        candidates = self._unique_carried_items(player_id)
        matches = _best_matches(query, candidates)
        return [item for _, item in matches]

    def player_stacks_matching(
        self, player_id: str, query: str
    ) -> list[tuple[ItemStack, Item]]:
        """Every carried stack matching query (exact or fuzzy), one entry per stack.

        Distinct from search_player_items: this returns the ItemStack rows
        themselves (not deduplicated), so callers can move/reduce quantity on
        a specific stack.
        """
        return _any_matches(query, self.stacks_carried_by(player_id))

    def expanded_player_instances(
        self, player_id: str, query: str
    ) -> list[tuple[ItemStack, Item]]:
        """Expand carried stacks into one entry per unit for indexed take/drop.

        A fungible stack with quantity 3 expands into three entries, all
        pointing at the same stack row (any unit is interchangeable); an
        instanced stack (quantity always 1) expands into a single entry.
        """
        instances: list[tuple[ItemStack, Item]] = []
        for stack, item in self.player_stacks_matching(player_id, query):
            instances.extend((stack, item) for _ in range(stack.quantity))
        return instances

    def expanded_room_instances(
        self, room_id: str, query: str
    ) -> list[tuple[ItemStack, Item]]:
        """Expand room stacks into one entry per unit for indexed take."""
        instances: list[tuple[ItemStack, Item]] = []
        for stack, item in self.search_in_room(room_id, query):
            instances.extend((stack, item) for _ in range(stack.quantity))
        return instances

    def find_in_room(
        self, room_id: str, name_or_id: str
    ) -> tuple[ItemStack, Item] | None:
        results = self.search_in_room(room_id, name_or_id)
        return results[0] if results else None

    def find_player_item(self, player_id: str, name_or_id: str) -> Item | None:
        results = self.search_player_items(player_id, name_or_id)
        return results[0] if results else None

    def _unique_carried_items(self, player_id: str) -> Iterable[tuple[ItemStack, Item]]:
        """Carried stacks deduplicated by item id, preserving first-seen order.

        Used by search_player_items, which reports distinct *items* (not stacks)
        for disambiguation prompts and use/give item resolution.
        """
        seen: set[str] = set()
        for stack, item in self.stacks_carried_by(player_id):
            if stack.item_id in seen:
                continue
            seen.add(stack.item_id)
            yield stack, item

    def _pair_with_items(
        self, stacks: Sequence[ItemStack]
    ) -> list[tuple[ItemStack, Item]]:
        items_by_id = self.get_many(stack.item_id for stack in stacks)
        paired: list[tuple[ItemStack, Item]] = []
        for stack in stacks:
            item = items_by_id.get(stack.item_id)
            if item is not None:
                paired.append((stack, item))
        return paired


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


def _match_kind(q: str, q_words: frozenset[str], item: Item) -> int:
    """0 = no match, 1 = fuzzy word-subset match, 2 = exact name/id/alias match."""
    if _item_matches_query(q, q_words, item):
        return 2
    if _item_matches_words(q_words, item):
        return 1
    return 0


def _best_matches(
    query: str, candidates: Iterable[tuple[_C, Item]]
) -> list[tuple[_C, Item]]:
    """The one item matcher: exact matches win; fall back to fuzzy matches
    only when there are no exact ones. Order is preserved within each bucket."""
    q = _normalize_item_name(query)
    q_words = _query_words(query)
    exact: list[tuple[_C, Item]] = []
    fuzzy: list[tuple[_C, Item]] = []
    for candidate, item in candidates:
        kind = _match_kind(q, q_words, item)
        if kind == 2:
            exact.append((candidate, item))
        elif kind == 1:
            fuzzy.append((candidate, item))
    return exact if exact else fuzzy


def _any_matches(
    query: str, candidates: Iterable[tuple[_C, Item]]
) -> list[tuple[_C, Item]]:
    """Every candidate matching query (exact or fuzzy), preserving position order.

    Used for indexed inventory slot selection, where each slot is an
    independent, positionally-addressable unit rather than a group to
    collapse down to "best" matches.
    """
    q = _normalize_item_name(query)
    q_words = _query_words(query)
    return [
        (candidate, item)
        for candidate, item in candidates
        if _match_kind(q, q_words, item) != 0
    ]
