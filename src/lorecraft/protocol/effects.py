"""Authoritative state-change effects — Python mirror of the Rust `Effect` enum.

Rust serializes `Effect` as an internally-tagged object (`#[serde(tag = "type")]`),
e.g. ``{"type": "MoveEntity", "entity": ..., "from": ..., "to": ...}``. Python lacks
Rust-style tagged enums, so each variant is a frozen dataclass sharing a base class;
``to_json``/``effect_from_json`` reproduce that exact ``{"type": ..., ...fields}``
wire shape so a value can be JSON-diffed against the Rust side.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import ClassVar

from lorecraft.errors import ValidationError
from lorecraft.types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class Effect:
    """Base class for the six effect variants.

    ``TAG`` is the serde discriminator value (the Rust variant name); subclasses
    set it as a class attribute. The base is never instantiated directly.
    """

    TAG: ClassVar[str] = ""

    def to_json(self) -> JsonObject:
        """Serialize to the ``{"type": TAG, ...fields}`` shape Rust emits."""
        payload: JsonObject = {"type": self.TAG}
        for f in fields(self):
            payload[f.name] = getattr(self, f.name)
        return payload


@dataclass(frozen=True, slots=True)
class MoveEntity(Effect):
    """Move an entity from one container/location to another."""

    TAG: ClassVar[str] = "MoveEntity"
    entity: str
    from_: str
    to: str

    def to_json(self) -> JsonObject:
        # `from` is a Python keyword; the field is `from_` but the wire key is `from`.
        return {
            "type": self.TAG,
            "entity": self.entity,
            "from": self.from_,
            "to": self.to,
        }


@dataclass(frozen=True, slots=True)
class TransferItem(Effect):
    """Transfer a quantity of an item between two owners/locations."""

    TAG: ClassVar[str] = "TransferItem"
    item: str
    from_: str
    to: str
    quantity: int

    def to_json(self) -> JsonObject:
        return {
            "type": self.TAG,
            "item": self.item,
            "from": self.from_,
            "to": self.to,
            "quantity": self.quantity,
        }


@dataclass(frozen=True, slots=True)
class AdjustMeter(Effect):
    """Adjust a numeric meter by a signed delta."""

    TAG: ClassVar[str] = "AdjustMeter"
    entity: str
    meter: str
    delta: int


@dataclass(frozen=True, slots=True)
class SetFlag(Effect):
    """Set (or overwrite) a flag on an entity to an arbitrary JSON value."""

    TAG: ClassVar[str] = "SetFlag"
    entity: str
    key: str
    value: JsonValue


@dataclass(frozen=True, slots=True)
class EmitEvent(Effect):
    """Emit a domain event for downstream handlers."""

    TAG: ClassVar[str] = "EmitEvent"
    event_type: str
    payload: JsonValue


@dataclass(frozen=True, slots=True)
class SendNarration(Effect):
    """Emit narration ordered relative to state effects. Command handlers narrate
    through ``OutboundMessage.Feed`` instead."""

    TAG: ClassVar[str] = "SendNarration"
    text: str
    message_type: str


_EFFECT_VARIANTS: dict[str, type[Effect]] = {
    cls.TAG: cls
    for cls in (
        MoveEntity,
        TransferItem,
        AdjustMeter,
        SetFlag,
        EmitEvent,
        SendNarration,
    )
}


def effect_from_json(data: JsonObject) -> Effect:
    """Reconstruct an ``Effect`` variant from its tagged-JSON shape."""
    tag = data.get("type")
    if not isinstance(tag, str) or tag not in _EFFECT_VARIANTS:
        raise ValidationError(f"unknown effect type: {tag!r}")
    cls = _EFFECT_VARIANTS[tag]
    if cls is MoveEntity:
        return MoveEntity(
            entity=_s(data, "entity"), from_=_s(data, "from"), to=_s(data, "to")
        )
    if cls is TransferItem:
        return TransferItem(
            item=_s(data, "item"),
            from_=_s(data, "from"),
            to=_s(data, "to"),
            quantity=_i(data, "quantity"),
        )
    if cls is AdjustMeter:
        return AdjustMeter(
            entity=_s(data, "entity"), meter=_s(data, "meter"), delta=_i(data, "delta")
        )
    if cls is SetFlag:
        return SetFlag(
            entity=_s(data, "entity"), key=_s(data, "key"), value=data.get("value")
        )
    if cls is EmitEvent:
        return EmitEvent(event_type=_s(data, "event_type"), payload=data.get("payload"))
    return SendNarration(text=_s(data, "text"), message_type=_s(data, "message_type"))


def _s(data: JsonObject, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValidationError(f"effect field {key!r} must be a string, got {value!r}")
    return value


def _i(data: JsonObject, key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"effect field {key!r} must be an int, got {value!r}")
    return value
