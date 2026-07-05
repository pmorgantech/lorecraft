"""Unit tests for `web.auth.login_or_register` — password creation/verification,
account claiming for pre-existing passwordless players, and token issuance."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.models.player import Player
from lorecraft.models.world import Room
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.web.auth import (
    InvalidCredentialsError,
    InvalidUsernameError,
    StartRoomNotConfiguredError,
    decode_player_access_token,
    issue_access_token,
    issue_refresh_token,
    login_or_register,
)

_SECRET = "test-secret-32-chars-long-enough!"
_START_ROOM = "village_square"


def _engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        session.add(
            Room(
                id=_START_ROOM,
                name="Village Square",
                description="A square.",
                map_x=0,
                map_y=0,
            )
        )
        session.commit()
    return engine


def test_first_login_creates_account() -> None:
    engine = _engine()
    with Session(engine) as session:
        room_repo = RoomRepo(session)
        result = login_or_register(
            session, room_repo, "newplayer", "hunter2", start_room=_START_ROOM
        )
        session.commit()
        assert result.created is True
        assert result.player.username == "newplayer"
        assert result.player.current_room_id == _START_ROOM


def test_second_login_verifies_password() -> None:
    engine = _engine()
    with Session(engine) as session:
        room_repo = RoomRepo(session)
        first = login_or_register(
            session, room_repo, "returning", "hunter2", start_room=_START_ROOM
        )
        session.commit()
        first_id = first.player.id

    with Session(engine) as session:
        room_repo = RoomRepo(session)
        second = login_or_register(
            session, room_repo, "returning", "hunter2", start_room=_START_ROOM
        )
    assert second.created is False
    assert second.player.id == first_id


def test_wrong_password_is_rejected() -> None:
    engine = _engine()
    with Session(engine) as session:
        room_repo = RoomRepo(session)
        login_or_register(
            session, room_repo, "someone", "correct-password", start_room=_START_ROOM
        )
        session.commit()

    with Session(engine) as session:
        room_repo = RoomRepo(session)
        try:
            login_or_register(
                session, room_repo, "someone", "wrong-password", start_room=_START_ROOM
            )
            assert False, "expected InvalidCredentialsError"
        except InvalidCredentialsError:
            pass


def test_invalid_username_is_rejected() -> None:
    engine = _engine()
    with Session(engine) as session:
        room_repo = RoomRepo(session)
        try:
            login_or_register(
                session, room_repo, "a", "hunter2", start_room=_START_ROOM
            )
            assert False, "expected InvalidUsernameError"
        except InvalidUsernameError:
            pass


def test_unconfigured_start_room_raises() -> None:
    engine = _engine()
    with Session(engine) as session:
        room_repo = RoomRepo(session)
        try:
            login_or_register(
                session, room_repo, "newplayer", "hunter2", start_room="nowhere"
            )
            assert False, "expected StartRoomNotConfiguredError"
        except StartRoomNotConfiguredError:
            pass


def test_login_claims_preexisting_passwordless_player() -> None:
    """A dev-seeded or pre-auth player with no PlayerAuth row can be claimed
    by the first successful login for that username, rather than erroring."""
    engine = _engine()
    with Session(engine) as session:
        session.add(
            Player(
                id="player-1",
                username="player-1",
                current_room_id=_START_ROOM,
                respawn_room_id=_START_ROOM,
                visited_rooms=[_START_ROOM],
            )
        )
        session.commit()

    with Session(engine) as session:
        room_repo = RoomRepo(session)
        result = login_or_register(
            session, room_repo, "player-1", "newpassword", start_room=_START_ROOM
        )
        session.commit()
        assert result.player.id == "player-1"

    # Subsequent login now requires the password that was just set.
    with Session(engine) as session:
        room_repo = RoomRepo(session)
        try:
            login_or_register(
                session, room_repo, "player-1", "wrong", start_room=_START_ROOM
            )
            assert False, "expected InvalidCredentialsError"
        except InvalidCredentialsError:
            pass


def test_access_token_round_trip() -> None:
    token = issue_access_token("player-42", _SECRET, ttl_seconds=3600)
    assert decode_player_access_token(token, _SECRET) == "player-42"


def test_refresh_token_is_not_accepted_as_access_token() -> None:
    token = issue_refresh_token("player-42", _SECRET, ttl_seconds=3600)
    assert decode_player_access_token(token, _SECRET) is None


def test_expired_access_token_is_rejected() -> None:
    token = issue_access_token("player-42", _SECRET, ttl_seconds=-1)
    assert decode_player_access_token(token, _SECRET) is None
