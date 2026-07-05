from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.models.player import Player
from lorecraft.models.world import Exit, Room
from lorecraft.engine.repos import RoomRepo
from lorecraft.web.rendering import CARTOGRAPHY_REVEAL_THRESHOLD, build_map_data


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

        map_data = build_map_data(room_repo, player, current_room)

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

        map_data = build_map_data(room_repo, player, current_room)

    by_id = {room["id"]: room for room in map_data["nearby_rooms"]}
    current = by_id["forge"]
    previous = by_id["square"]
    assert previous["py"] > current["py"]
    assert previous["px"] == current["px"]


def _seed_two_room_world(session: Session) -> RoomRepo:
    room_repo = RoomRepo(session)
    room_repo.add(Room(id="start", name="Start", description="d", map_x=0, map_y=0))
    room_repo.add(Room(id="next", name="Next", description="d", map_x=1, map_y=0))
    session.add(
        Exit(room_id="start", direction="east", target_room_id="next", hidden=False)
    )
    session.commit()
    return room_repo


def test_full_map_without_cartography_does_not_reveal_unvisited_rooms() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        room_repo = _seed_two_room_world(session)
        player = Player(
            id="player-1",
            username="player-1",
            current_room_id="start",
            respawn_room_id="start",
            visited_rooms=["start"],
        )
        current_room = room_repo.get("start")

        map_data = build_map_data(
            room_repo, player, current_room, full=True, cartography_level=0
        )

    assert {r["id"] for r in map_data["nearby_rooms"]} == {"start"}


def test_full_map_with_cartography_reveals_adjacent_unvisited_room() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        room_repo = _seed_two_room_world(session)
        player = Player(
            id="player-1",
            username="player-1",
            current_room_id="start",
            respawn_room_id="start",
            visited_rooms=["start"],
        )
        current_room = room_repo.get("start")

        map_data = build_map_data(
            room_repo,
            player,
            current_room,
            full=True,
            cartography_level=CARTOGRAPHY_REVEAL_THRESHOLD,
        )

    by_id = {r["id"]: r for r in map_data["nearby_rooms"]}
    assert set(by_id) == {"start", "next"}
    assert by_id["next"]["visited"] is False
    assert by_id["next"]["name"] == "Unexplored"
    assert by_id["start"]["visited"] is True


def test_full_map_cartography_reveal_excludes_hidden_exits() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        room_repo = RoomRepo(session)
        room_repo.add(Room(id="start", name="Start", description="d", map_x=0, map_y=0))
        room_repo.add(
            Room(id="secret", name="Secret", description="d", map_x=1, map_y=0)
        )
        session.add(
            Exit(
                room_id="start",
                direction="east",
                target_room_id="secret",
                hidden=True,
            )
        )
        session.commit()

        player = Player(
            id="player-1",
            username="player-1",
            current_room_id="start",
            respawn_room_id="start",
            visited_rooms=["start"],
        )
        current_room = room_repo.get("start")

        map_data = build_map_data(
            room_repo,
            player,
            current_room,
            full=True,
            cartography_level=CARTOGRAPHY_REVEAL_THRESHOLD,
        )

    assert {r["id"] for r in map_data["nearby_rooms"]} == {"start"}


def test_non_full_map_ignores_cartography_level() -> None:
    """The sidebar minimap (full=False) never expands beyond visited rooms,
    regardless of cartography level — that's the full-screen modal's job."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        room_repo = _seed_two_room_world(session)
        player = Player(
            id="player-1",
            username="player-1",
            current_room_id="start",
            respawn_room_id="start",
            visited_rooms=["start"],
        )
        current_room = room_repo.get("start")

        map_data = build_map_data(
            room_repo,
            player,
            current_room,
            full=False,
            cartography_level=CARTOGRAPHY_REVEAL_THRESHOLD,
        )

    assert {r["id"] for r in map_data["nearby_rooms"]} == {"start"}
