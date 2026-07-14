"""Player activity gates for rest/sleep-style busy states."""

from __future__ import annotations

from dataclasses import dataclass

from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import WorldClock

RESTING_FLAG = "condition:resting"
SLEEP_UNTIL_FLAG = "condition:sleeping_until"

_REST_ALLOWED_VERBS = frozenset(
    {"help", "inventory", "look", "quit", "rest", "save", "sleep", "stand"}
)


@dataclass(frozen=True)
class ActivityBlock:
    reason: str


def is_resting(player: Player) -> bool:
    return bool(player.flags.get(RESTING_FLAG))


def sleep_until(player: Player) -> float | None:
    raw = player.flags.get(SLEEP_UNTIL_FLAG)
    if isinstance(raw, int | float):
        return float(raw)
    return None


def is_sleeping(player: Player, clock: WorldClock | None) -> bool:
    until = sleep_until(player)
    if until is None:
        return False
    if clock is None:
        return True
    return clock.game_epoch < until


def clear_expired_sleep(player: Player, clock: WorldClock | None) -> bool:
    until = sleep_until(player)
    if until is None or clock is None or clock.game_epoch < until:
        return False
    flags = dict(player.flags)
    flags.pop(SLEEP_UNTIL_FLAG, None)
    player.flags = flags
    return True


def set_resting(player: Player, resting: bool) -> None:
    flags = dict(player.flags)
    if resting:
        flags[RESTING_FLAG] = True
    else:
        flags.pop(RESTING_FLAG, None)
    player.flags = flags


def set_sleeping_until(player: Player, epoch: float) -> None:
    flags = dict(player.flags)
    flags.pop(RESTING_FLAG, None)
    flags[SLEEP_UNTIL_FLAG] = epoch
    player.flags = flags


def clear_sleeping(player: Player) -> None:
    flags = dict(player.flags)
    flags.pop(SLEEP_UNTIL_FLAG, None)
    player.flags = flags


def command_activity_block(
    player: Player, clock: WorldClock | None, verb: str
) -> ActivityBlock | None:
    if clear_expired_sleep(player, clock):
        return None
    if is_sleeping(player, clock):
        return ActivityBlock("You are asleep and can't do anything yet.")
    if is_resting(player) and verb not in _REST_ALLOWED_VERBS:
        return ActivityBlock("You are resting. Stand up first.")
    return None


def sleeping_player_ids(players: list[Player], clock: WorldClock | None) -> set[str]:
    return {player.id for player in players if is_sleeping(player, clock)}
