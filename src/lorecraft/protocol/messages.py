"""Outbound client messages — Python mirror of the Rust `OutboundMessage` enum.

Same internally-tagged wire shape as `effects.py`: ``{"type": "Feed", ...}`` /
``{"type": "PanelUpdate", ...}``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import ClassVar

from lorecraft.errors import ValidationError
from lorecraft.types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    """Base class for the two outbound-message variants."""

    TAG: ClassVar[str] = ""

    def to_json(self) -> JsonObject:
        """Serialize to the ``{"type": TAG, ...fields}`` shape Rust emits."""
        payload: JsonObject = {"type": self.TAG}
        for f in fields(self):
            payload[f.name] = getattr(self, f.name)
        return payload


@dataclass(frozen=True, slots=True)
class Feed(OutboundMessage):
    """A narrative feed line — maps to the engine's ``ctx.say``."""

    TAG: ClassVar[str] = "Feed"
    text: str
    message_type: str


@dataclass(frozen=True, slots=True)
class PanelUpdate(OutboundMessage):
    """A client panel refresh keyed by panel name — maps to ``ctx.push_update``.

    A client-side refresh hint, not an authoritative state change.
    """

    TAG: ClassVar[str] = "PanelUpdate"
    key: str
    value: JsonValue


_MESSAGE_VARIANTS: dict[str, type[OutboundMessage]] = {
    cls.TAG: cls for cls in (Feed, PanelUpdate)
}


def message_from_json(data: JsonObject) -> OutboundMessage:
    """Reconstruct an ``OutboundMessage`` variant from its tagged-JSON shape."""
    tag = data.get("type")
    if not isinstance(tag, str) or tag not in _MESSAGE_VARIANTS:
        raise ValidationError(f"unknown outbound message type: {tag!r}")
    if _MESSAGE_VARIANTS[tag] is Feed:
        text = data.get("text")
        message_type = data.get("message_type")
        if not isinstance(text, str) or not isinstance(message_type, str):
            raise ValidationError("Feed requires string text and message_type")
        return Feed(text=text, message_type=message_type)
    key = data.get("key")
    if not isinstance(key, str):
        raise ValidationError("PanelUpdate requires a string key")
    return PanelUpdate(key=key, value=data.get("value"))
