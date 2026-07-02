"""Shared structural types used by early engine scaffolding."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TYPE_CHECKING, Protocol, TypeAlias

if TYPE_CHECKING:
    from lorecraft.game.context import GameContext


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class MessageSink(Protocol):
    def say(self, text: str) -> None: ...


class RoomState(Protocol):
    @property
    def disabled_commands(self) -> list[str]: ...

    @property
    def light_level(self) -> int: ...


class PlayerState(Protocol):
    @property
    def active_combat_session_id(self) -> str | None: ...

    @property
    def flags(self) -> dict[str, JsonValue]: ...

    @property
    def inventory(self) -> list[str]: ...


class CommandContext(Protocol):
    player: PlayerState
    room: RoomState


class JsonWebSocket(Protocol):
    def accept(self) -> Awaitable[None]: ...

    def send_json(self, data: JsonObject) -> Awaitable[None]: ...


class CommandHandler(Protocol):
    """A command handler — must accept noun and GameContext, return None."""

    def __call__(self, noun: str | None, ctx: GameContext) -> None: ...
