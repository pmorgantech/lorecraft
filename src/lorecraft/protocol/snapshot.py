"""Opaque entity snapshot — Python mirror of the Rust `EntitySnapshot`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from lorecraft.protocol._coerce import require_dict, require_str
from lorecraft.types import JsonObject, JsonValue


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

    def to_json(self) -> JsonObject:
        # `attributes` is already a JSON value bag; copy so the wire dict can't
        # alias this frozen instance's mapping.
        return {"id": self.id, "kind": self.kind, "attributes": dict(self.attributes)}

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        return cls(
            id=require_str(data, "id"),
            kind=require_str(data, "kind"),
            attributes=dict(require_dict(data, "attributes")),
        )
