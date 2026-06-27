"""Shared structural types used by early engine scaffolding."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol, TypeAlias


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class MessageSink(Protocol):
    def say(self, text: str) -> None: ...


class RoomState(Protocol):
    disabled_commands: list[str]
    light_level: int


class PlayerState(Protocol):
    active_combat_session_id: str | None
    flags: dict[str, JsonValue]
    inventory: list[str]


class CommandContext(Protocol):
    player: PlayerState
    room: RoomState


class JsonWebSocket(Protocol):
    def accept(self) -> Awaitable[None]: ...

    def send_json(self, message: JsonObject) -> Awaitable[None]: ...
