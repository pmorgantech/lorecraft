"""Player-facing authentication API.

Local username+password auth for LAN-party deployments (see
`docs/player_authentication.md`). First successful login for a username
creates the account atomically; subsequent logins verify the stored
password hash. Issues short-lived JWT access tokens (15 min default) and
longer-lived refresh tokens (8h default) that rotate on every use, signed
with `Settings.player_session_secret` — the same secret that signs the
browser's `lorecraft_session` cookie, but a distinct token `type` so the
two can never be replayed as each other.

`login_or_register()` is also the function the browser lobby routes
(`web/frontend.py`'s `/lobby/enter`/`/lobby/create`) call, so there is one
password-checking code path for both the JSON API and the HTMX UI.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from lorecraft.admin.auth import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from lorecraft.models.player import Player
from lorecraft.models.player_auth import PlayerAuth
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.web.session import get_app_state, get_engines, player_session_secret

log = logging.getLogger(__name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,30}$")

_PROVIDER_LOCAL = "local"
_ROLE = "player"


class InvalidUsernameError(ValueError):
    """Username fails format validation."""


class InvalidCredentialsError(ValueError):
    """Username exists but the password is wrong (or account can't be used)."""


class StartRoomNotConfiguredError(RuntimeError):
    """The configured spawn room doesn't exist — a server config error."""


class LoginResult:
    __slots__ = ("player", "created")

    def __init__(self, player: Player, created: bool) -> None:
        self.player = player
        self.created = created


def login_or_register(
    db: DBSession,
    room_repo: RoomRepo,
    username: str,
    password: str,
    *,
    start_room: str,
) -> LoginResult:
    """Verify an existing local account or create one on first login.

    Three cases:
    1. A `PlayerAuth` row already exists for this username — verify the
       password against its hash.
    2. No `PlayerAuth` row, but a `Player` with this username already
       exists (e.g. a dev-seeded player, or one created before auth
       existed) — this login *claims* it: binds a new credential to the
       existing player rather than erroring, so pre-existing seed/dev
       players keep working once a password is set for them.
    3. Neither exists — create a brand new `Player` + `PlayerAuth`.
    """
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise InvalidUsernameError(
            "Username must be 3-30 characters: letters, numbers, - or _ only."
        )

    player_repo = PlayerRepo(db)
    now = time.time()

    existing_auth = player_repo.auth_by_subject(_PROVIDER_LOCAL, username)
    if existing_auth is not None:
        if not verify_password(password, existing_auth.credential_hash or ""):
            raise InvalidCredentialsError("Invalid username or password.")
        player = player_repo.get(existing_auth.player_id)
        if player is None:
            raise InvalidCredentialsError("Invalid username or password.")
        existing_auth.last_login_at = now
        return LoginResult(player=player, created=False)

    existing_player = player_repo.by_username(username)
    if existing_player is not None:
        auth = PlayerAuth(
            player_id=existing_player.id,
            provider=_PROVIDER_LOCAL,
            provider_subject=username,
            credential_hash=hash_password(password),
            created_at=now,
            last_login_at=now,
        )
        player_repo.add_auth(auth)
        return LoginResult(player=existing_player, created=False)

    if room_repo.get(start_room) is None:
        raise StartRoomNotConfiguredError("Starting room is not configured.")

    player = Player(
        id=str(uuid.uuid4()),
        username=username,
        current_room_id=start_room,
        respawn_room_id=start_room,
        visited_rooms=[start_room],
    )
    player_repo.add(player)
    db.flush()
    auth = PlayerAuth(
        player_id=player.id,
        provider=_PROVIDER_LOCAL,
        provider_subject=username,
        credential_hash=hash_password(password),
        created_at=now,
        last_login_at=now,
    )
    player_repo.add_auth(auth)
    return LoginResult(player=player, created=True)


def issue_access_token(player_id: str, secret: str, ttl_seconds: int) -> str:
    return create_token(player_id, _ROLE, secret, ttl_seconds, "access")


def issue_refresh_token(player_id: str, secret: str, ttl_seconds: int) -> str:
    return create_token(player_id, _ROLE, secret, ttl_seconds, "refresh")


def decode_player_access_token(token: str, secret: str) -> str | None:
    """Return the player id from a valid, unexpired access token, else None."""
    try:
        payload = decode_token(token, secret)
    except jwt.InvalidTokenError:
        return None
    if payload.token_type != "access":
        return None
    return payload.username


# ---------------------------------------------------------------------------
# Router: POST /auth/login (JSON API)
# ---------------------------------------------------------------------------


class LoginBody(BaseModel):
    username: str
    password: str


router = APIRouter(prefix="/auth", tags=["player-auth"])


@router.post("/login")
async def login(body: LoginBody, request: Request) -> dict[str, object]:
    app_state = get_app_state(request)
    if app_state is None:
        raise HTTPException(status_code=500, detail="Server not ready")
    game_engine, _ = get_engines(request)
    start_room = app_state.settings.seed_player_start_room

    with DBSession(game_engine) as db:
        room_repo = RoomRepo(db)
        try:
            result = login_or_register(
                db, room_repo, body.username, body.password, start_room=start_room
            )
        except InvalidUsernameError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except InvalidCredentialsError as e:
            raise HTTPException(status_code=401, detail=str(e)) from e
        except StartRoomNotConfiguredError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        db.commit()
        player_id = result.player.id
        created = result.created

    secret = player_session_secret(app_state)
    access_ttl = app_state.settings.player_access_token_ttl_seconds
    refresh_ttl = app_state.settings.player_refresh_token_ttl_seconds
    return {
        "access_token": issue_access_token(player_id, secret, access_ttl),
        "refresh_token": issue_refresh_token(player_id, secret, refresh_ttl),
        "token_type": "bearer",
        "expires_in": access_ttl,
        "player_id": player_id,
        "created": created,
    }
