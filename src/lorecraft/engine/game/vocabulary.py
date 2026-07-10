"""Vocabulary governance: self-describing descriptors for the scripting "language".

See ``docs/scripting_engine_design.md`` §8. Every condition / effect / behavior-mode in
the declarative scripting vocabulary registers a *descriptor* (name + typed params +
subject role + what it reads/writes + category + human doc + a **capability signature**)
rather than a bare string. That self-description buys three things:

* **Auto-discovery** — the catalog (and the generated builder-guide API doc) is rendered
  *from* these descriptors, so it can never drift from the code (``Vocabulary.to_json``).
* **Author-time linting** — a name/param lookup validates ``when:``/``do:`` blocks in
  world YAML before they ship (fail-closed), while the runtime stays fail-open.
* **Duplication detection** — two differently-named entries that resolve to the same
  :class:`CapabilitySig` are almost certainly the same thing wearing two names (the
  ``min_reputation`` / ``reputation_at_least`` drift this whole effort exists to kill).
  :meth:`Vocabulary.overlaps` surfaces them so CI can reject the second one.

This module is pure Tier 1: descriptors + a catalog, no handler logic and no feature
imports. The existing condition/effect registries adopt these descriptors in follow-up
steps; the handler callables continue to live in their own registries.

There are **no aliases** — exactly one canonical name per capability, so the overlap rule
is absolute (any two names sharing a signature is a defect). This is distinct from the
player-facing command-verb alias mechanism (``look``/``l``), which is unrelated.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum

from lorecraft.types import JsonObject


class Subject(StrEnum):
    """Whose state a vocabulary entry reads or writes — a *role*, not an entity type.

    Using roles (rather than ``player_``/``npc_``/``object_`` name prefixes) is what makes
    the naming convention machine-checkable and the capability signature comparable across
    entries. See ``docs/scripting_engine_design.md`` §8.4.
    """

    SELF = "self"  # the entity the script is attached to (the NPC/room/item)
    ACTOR = "actor"  # the triggering party, usually the player
    TARGET = "target"  # an explicitly-named entity
    WORLD = "world"  # global / no specific subject (e.g. chance, season, time)


class VocabKind(StrEnum):
    CONDITION = "condition"  # a `when:` predicate
    EFFECT = "effect"  # a `do:` action
    BEHAVIOR_MODE = "behavior_mode"  # an NPC `behavior.mode`


class VocabularyError(Exception):
    """Raised on an exact-name collision when registering a descriptor."""


@dataclass(frozen=True)
class ParamSpec:
    """One parameter of a vocabulary entry, for validation and catalog rendering.

    ``type`` is a short schema token (``"str"``, ``"int"``, ``"float"``, ``"bool"``,
    ``"list[str]"``, or a semantic alias like ``"room_id"`` / ``"item_id"`` / ``"faction"``)
    — deliberately a string, not a Python type, so the descriptor stays trivially
    serializable for the generated catalog/builder-guide.
    """

    name: str
    type: str
    required: bool = True
    doc: str = ""

    def to_json(self) -> JsonObject:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "doc": self.doc,
        }


@dataclass(frozen=True)
class CapabilitySig:
    """The dedup key: two entries with an equal signature do the same job.

    * ``subject`` — whose state (``ACTOR``/``SELF``/``TARGET``/``WORLD``).
    * ``domain`` — the feature/state family it touches (``"reputation"``, ``"flags"``,
      ``"world_clock"``, ``"effects"``, …).
    * ``attribute`` — the specific thing within that domain (``"standing"``, ``"season"``,
      ``"<flag>"`` for parameterised targets, …).
    * ``op`` — for a condition, the comparator (``at_least``/``below``/``is``/``has``/
      ``lacks``); for an effect, the mutation verb (``set``/``clear``/``give``/``apply``/…).

    Two conditions that both mean "actor's reputation is at least N" share
    ``(ACTOR, "reputation", "standing", "at_least")`` regardless of what they're *named* —
    which is precisely how :meth:`Vocabulary.overlaps` catches an accidental synonym.
    """

    subject: Subject
    domain: str
    attribute: str
    op: str

    def __str__(self) -> str:
        return f"{self.subject.value}:{self.domain}:{self.attribute}:{self.op}"

    def to_json(self) -> JsonObject:
        return {
            "subject": self.subject.value,
            "domain": self.domain,
            "attribute": self.attribute,
            "op": self.op,
        }


@dataclass(frozen=True)
class VocabEntry:
    """A self-describing descriptor for one scripting-vocabulary name."""

    name: str
    kind: VocabKind
    subject: Subject
    category: str  # catalog grouping, e.g. "social" | "world_clock" | "flags"
    doc: str  # one-line human description (rendered into the builder guide)
    capability: CapabilitySig
    params: tuple[ParamSpec, ...] = field(default_factory=tuple)

    def to_json(self) -> JsonObject:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "subject": self.subject.value,
            "category": self.category,
            "doc": self.doc,
            "capability": self.capability.to_json(),
            "params": [p.to_json() for p in self.params],
        }


class Vocabulary:
    """The governed catalog: register descriptors, detect collisions & overlaps, serialize.

    Registration enforces exactly one canonical name per entry (an exact-name collision is
    a hard error — the previous silent-overwrite behaviour is what let duplicates
    accumulate). Capability *overlaps* across different names are not raised at registration
    (a feature can't see the others at import time); they're reported by :meth:`overlaps`
    for a CI check to gate on.
    """

    def __init__(self) -> None:
        self._entries: dict[str, VocabEntry] = {}

    def register(self, entry: VocabEntry) -> VocabEntry:
        existing = self._entries.get(entry.name)
        if existing is not None:
            raise VocabularyError(
                f"duplicate vocabulary name {entry.name!r} "
                f"(already registered as {existing.kind.value}); "
                "names must be unique — no aliases (see docs/scripting_engine_design.md §8.6)"
            )
        self._entries[entry.name] = entry
        return entry

    def get(self, name: str) -> VocabEntry | None:
        return self._entries.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def all(self) -> list[VocabEntry]:
        """All entries, sorted by (category, name) for stable catalog output."""
        return sorted(self._entries.values(), key=lambda e: (e.category, e.name))

    def by_category(self) -> dict[str, list[VocabEntry]]:
        grouped: dict[str, list[VocabEntry]] = defaultdict(list)
        for entry in self.all():
            grouped[entry.category].append(entry)
        return dict(grouped)

    def overlaps(self) -> list[tuple[VocabEntry, ...]]:
        """Groups of 2+ entries sharing one capability signature — likely duplicates.

        This is the self-check against accidental re-invention (§8.3): any group returned
        here means two names do the same job and one should be removed. Returned groups are
        sorted by name for deterministic CI output; an empty list means the vocabulary is
        duplicate-free.
        """
        by_sig: dict[CapabilitySig, list[VocabEntry]] = defaultdict(list)
        for entry in self._entries.values():
            by_sig[entry.capability].append(entry)
        clashes = [
            tuple(sorted(group, key=lambda e: e.name))
            for group in by_sig.values()
            if len(group) > 1
        ]
        return sorted(clashes, key=lambda group: group[0].name)

    def to_json(self) -> JsonObject:
        """Serialize the whole catalog — the source for the generated builder-guide doc."""
        return {"entries": [entry.to_json() for entry in self.all()]}
