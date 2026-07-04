"""Per-player hidden-exit discovery tracking (Sprint 25.1).

Discovery is per-player, stored in the existing Player.flags dict (the same
mechanism dialogue/quest state already uses) — no new table needed. A
discovered hidden exit stays discovered; it isn't a room-global reveal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lorecraft.game.context import GameContext

_DISCOVERED_EXIT_PREFIX = "_discovered_exit"


def _flag_key(room_id: str, direction: str) -> str:
    return f"{_DISCOVERED_EXIT_PREFIX}:{room_id}:{direction}"


def is_exit_discovered(ctx: "GameContext", room_id: str, direction: str) -> bool:
    return bool(ctx.player.flags.get(_flag_key(room_id, direction)))


def mark_exit_discovered(ctx: "GameContext", room_id: str, direction: str) -> None:
    key = _flag_key(room_id, direction)
    if not ctx.player.flags.get(key):
        ctx.player.flags = {**ctx.player.flags, key: True}
