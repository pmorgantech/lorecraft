"""Typed JSON extraction helpers shared by the protocol containers' ``from_json``.

The container types (`ScriptResult`, `CommandOutcome`, …) reconstruct themselves
from untrusted ``dict`` input, so a missing/mistyped field must surface as a typed
``ValidationError`` rather than a silent ``KeyError``/``TypeError`` or a mangled
value. These mirror the private ``_s``/``_i`` guards in ``effects.py`` but are
shared so the nine container types don't each re-implement them.
"""

from __future__ import annotations

from lorecraft.errors import ValidationError
from lorecraft.types import JsonObject, JsonValue


def require_str(data: JsonObject, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValidationError(f"field {key!r} must be a string, got {value!r}")
    return value


def require_int(data: JsonObject, key: str) -> int:
    value = data.get(key)
    # bool is an int subclass; reject it so a stray True/False can't pose as 0/1.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"field {key!r} must be an int, got {value!r}")
    return value


def optional_int(data: JsonObject, key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"field {key!r} must be an int or null, got {value!r}")
    return value


def require_dict(data: JsonObject, key: str) -> JsonObject:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValidationError(f"field {key!r} must be an object, got {value!r}")
    return value


def require_list(data: JsonObject, key: str) -> list[JsonValue]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValidationError(f"field {key!r} must be an array, got {value!r}")
    return value


def require_str_list(data: JsonObject, key: str) -> list[str]:
    items = require_list(data, key)
    for item in items:
        if not isinstance(item, str):
            raise ValidationError(f"field {key!r} must be an array of strings")
    return [item for item in items if isinstance(item, str)]


def require_object(value: JsonValue) -> JsonObject:
    """Assert an already-extracted list element is a JSON object."""
    if not isinstance(value, dict):
        raise ValidationError(f"expected a nested object, got {value!r}")
    return value
