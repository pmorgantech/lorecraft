from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.models.player import Player
from lorecraft.models.world import Room
from lorecraft.repos import RoomRepo
from lorecraft.web.frontend import _build_map_data


def test_build_map_data_handles_equal_distance_rooms() -> None:
    """Rooms equidistant from the current room must not trigger Room comparison."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        room_repo = RoomRepo(session)
        room_repo.add(
            Room(
                id="center",
                name="Center",
                description="Center room.",
                map_x=0,
                map_y=0,
            )
        )
        room_repo.add(
            Room(
                id="north",
                name="North",
                description="North room.",
                map_x=0,
                map_y=1,
            )
        )
        room_repo.add(
            Room(
                id="east",
                name="East",
                description="East room.",
                map_x=1,
                map_y=0,
            )
        )
        session.commit()

        player = Player(
            id="player-1",
            username="player-1",
            current_room_id="center",
            respawn_room_id="center",
            visited_rooms=["center", "north", "east"],
        )
        current_room = room_repo.get("center")

        map_data = _build_map_data(room_repo, player, current_room)

    assert len(map_data["nearby_rooms"]) == 3
    assert {room["id"] for room in map_data["nearby_rooms"]} == {
        "center",
        "north",
        "east",
    }
    current = next(room for room in map_data["nearby_rooms"] if room["current"])
    assert current["id"] == "center"

    by_id = {room["id"]: room for room in map_data["nearby_rooms"]}
    assert by_id["north"]["py"] < current["py"]
    assert by_id["east"]["px"] > current["px"]


def test_build_map_data_north_travel_places_previous_room_south() -> None:
    """After moving north, the prior room should render below the current dot."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        room_repo = RoomRepo(session)
        room_repo.add(
            Room(
                id="square",
                name="Square",
                description="Town square.",
                map_x=4,
                map_y=8,
            )
        )
        room_repo.add(
            Room(
                id="forge",
                name="Forge",
                description="Blacksmith forge.",
                map_x=4,
                map_y=9,
            )
        )
        session.commit()

        player = Player(
            id="player-1",
            username="player-1",
            current_room_id="forge",
            respawn_room_id="square",
            visited_rooms=["square", "forge"],
        )
        current_room = room_repo.get("forge")

        map_data = _build_map_data(room_repo, player, current_room)

    by_id = {room["id"]: room for room in map_data["nearby_rooms"]}
    current = by_id["forge"]
    previous = by_id["square"]
    assert previous["py"] > current["py"]
    assert previous["px"] == current["px"]
