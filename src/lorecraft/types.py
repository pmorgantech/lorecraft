"""Shared structural types used by early engine scaffolding."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TYPE_CHECKING, Protocol, TypeAlias, TypedDict

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext


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


class CommandContext(Protocol):
    player: PlayerState
    room: RoomState


class JsonWebSocket(Protocol):
    def accept(self) -> Awaitable[None]: ...

    def send_json(self, data: JsonObject) -> Awaitable[None]: ...


class CommandHandler(Protocol):
    """A command handler — must accept noun and GameContext, return None."""

    def __call__(self, noun: str | None, ctx: GameContext) -> None: ...


# WebSocket and API payload schemas


class WsFeedAppend(TypedDict):
    """WebSocket feed_append message."""

    type: str  # "feed_append"
    content: str
    message_type: str


class WsStateChange(TypedDict):
    """WebSocket state_change message."""

    type: str  # "state_change"
    affected_panels: list[str]
    actor_id: str


class WsPlayerLeft(TypedDict):
    """WebSocket player_left message."""

    type: str  # "player_left"
    player_id: str
    username: str
    presence: str


class WsNarrative(TypedDict):
    """WebSocket narrative message."""

    type: str  # "narrative"
    html: str


class InventoryEntry(TypedDict):
    """One carried item-stack, as pushed in the "inventory" update key (Sprint 16).

    Replaces the old flat list[str] of item ids; a stack now carries its own
    quantity and (if instanced) identity, instead of being repeated N times.
    """

    item_id: str
    name: str
    quantity: int
    instance_id: str | None


class ApiStatusResponse(TypedDict, total=False):
    """Common API response with status field."""

    status: str
    player_id: str
    room_id: str
    id: str
    version: int
    username: str
