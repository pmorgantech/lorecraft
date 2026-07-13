"""Opaque entity snapshot — Python mirror of the Rust `EntitySnapshot`."""

from __future__ import annotations

from dataclasses import dataclass, field

from lorecraft.types import JsonValue


@dataclass(frozen=True, slots=True)
class EntitySnapshot:
    """An immutable, opaque view of a game entity for script/effect evaluation.

    The mechanism layer knows only ``id``, ``kind``, and a bag of ``attributes`` —
    it deliberately does *not* type feature-specific fields (a room's exits, a
    player's HP). Those are Tier 2 policy the feature fills into ``attributes``;
    adding a typed feature field here would leak policy into the mechanism layer.
    """

    id: str
    kind: str
    attributes: dict[str, JsonValue] = field(default_factory=dict)
