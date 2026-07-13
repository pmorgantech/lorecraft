"""Player-UI state projections for WebSocket frames.

These pure functions render a player's room, inventory, minimap, and world-time
into the JSON blobs the browser client expects on `connected`, `reconnect_sync`,
and `command_result` frames. They were factored out of `main.py` so both the
live `/ws` handler and the Rust-port gateway adapter
(`lorecraft.gateway.adapter`) build identical payloads from one place — no
presentation drift between the two transports. No behavior change from the
original `main.py` helpers.
"""

from __future__ import annotations

from lorecraft.engine.clock.celestial import moon_phase_for_day, tide_for_hour
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.types import JsonObject, JsonValue


def reconnect_sync_payload(
    player: Player, session_id: str, updates: JsonObject
) -> JsonObject:
    """The `reconnect_sync` frame replayed to a client resuming within grace."""
    return {
        "type": "reconnect_sync",
        "session_id": session_id,
        "player": {
            "id": player.id,
            "username": player.username,
            "current_room_id": player.current_room_id,
        },
        "room": updates["room"],
        "inventory": updates["inventory"],
        "time": updates["time"],
        "updates": updates,
    }


def player_ui_updates(
    player: Player,
    room: Room,
    room_repo: RoomRepo,
    item_repo: ItemRepo,
) -> JsonObject:
    """The `updates` blob (room + visited rooms + inventory + world time) sent on
    connect and after every command."""
    visited_rooms: list[JsonValue] = [
        _room_snapshot(visited_room, room_repo, visited_room_ids=player.visited_rooms)
        for visited_room in _visited_rooms(player, room_repo)
    ]
    return {
        "room_id": room.id,
        "room": _room_snapshot(room, room_repo, visited_room_ids=player.visited_rooms),
        "visited_rooms": visited_rooms,
        "inventory": _inventory_snapshot(player, item_repo),
        "time": _time_snapshot(room_repo),
    }


def _visited_rooms(player: Player, room_repo: RoomRepo) -> list[Room]:
    rooms: list[Room] = []
    for room_id in player.visited_rooms:
        room = room_repo.get(room_id)
        if room is not None:
            rooms.append(room)
    return rooms


def _room_snapshot(
    room: Room, room_repo: RoomRepo, *, visited_room_ids: list[str]
) -> JsonObject:
    exits: list[JsonValue] = []
    for exit_ in room_repo.exits(room.id):
        target_room = room_repo.get(exit_.target_room_id)
        target_payload: JsonObject = {
            "direction": exit_.direction,
            "target_room_id": exit_.target_room_id,
            "hidden": exit_.hidden,
            "locked": exit_.locked,
            "visited": exit_.target_room_id in visited_room_ids,
        }
        if target_room is not None:
            target_payload["target_map_x"] = target_room.map_x
            target_payload["target_map_y"] = target_room.map_y
            target_payload["target_map_z"] = target_room.map_z
        exits.append(target_payload)

    return {
        "id": room.id,
        "name": room.name,
        "description": room.description,
        "map_x": room.map_x,
        "map_y": room.map_y,
        "map_z": room.map_z,
        "exits": exits,
    }


def _inventory_snapshot(player: Player, item_repo: ItemRepo) -> list[JsonValue]:
    items: list[JsonValue] = []
    for stack, item in item_repo.stacks_carried_by(player.id):
        items.append(
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "quantity": stack.quantity,
            }
        )
    return items


def _time_snapshot(room_repo: RoomRepo) -> JsonObject:
    clock = room_repo.world_clock()
    if clock is None:
        return {}
    return {
        "hour": clock.current_hour,
        "minute": clock.current_minute,
        "day": clock.current_day,
        "season": clock.current_season,
        "weather": clock.weather,
        "moon": moon_phase_for_day(clock.current_day),
        "tide": tide_for_hour(clock.current_hour),
    }
