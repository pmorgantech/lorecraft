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
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.state import AppState
from lorecraft.web.player_auth import PLAYER_SESSION_COOKIE, decode_player_id
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


class PlayerNotFoundError(ValueError):
    """`allow_create=False` and no account exists for this username."""


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
    allow_create: bool = True,
) -> LoginResult:
    """Verify an existing local account, or create one on first login.

    Three cases:
    1. A `PlayerAuth` row already exists for this username — verify the
       password against its hash.
    2. No `PlayerAuth` row, but a `Player` with this username already
       exists (e.g. a dev-seeded player, or one created before auth
       existed) — this login *claims* it: binds a new credential to the
       existing player rather than erroring, so pre-existing seed/dev
       players keep working once a password is set for them.
    3. Neither exists — create a brand new `Player` + `PlayerAuth`, unless
       `allow_create=False` (the browser's "Log In" tab), in which case
       raise `PlayerNotFoundError` instead of silently creating an account
       for what may just be a typo'd username.
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

    if not allow_create:
        raise PlayerNotFoundError("No account with that name. Try Create Character.")

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


router = APIRouter(prefix="/auth", tags=["player-auth"])


# ---------------------------------------------------------------------------
# WebSocket tickets — single-use, short-TTL, in-memory (AppState.ws_tickets)
# ---------------------------------------------------------------------------


def issue_ws_ticket(app_state: AppState, player_id: str) -> str:
    """Mint a single-use ticket mapping to `player_id`, valid for a short TTL."""
    _prune_expired_tickets(app_state)
    ticket = uuid.uuid4().hex
    expires_at = time.time() + app_state.settings.player_ws_ticket_ttl_seconds
    app_state.ws_tickets[ticket] = (player_id, expires_at)
    return ticket


def consume_ws_ticket(app_state: AppState, ticket: str) -> str | None:
    """Atomically look up and invalidate a ticket. Returns the player id, or
    None if the ticket doesn't exist or has expired (stealing an already-used
    or expired ticket is therefore useless)."""
    entry = app_state.ws_tickets.pop(ticket, None)
    if entry is None:
        return None
    player_id, expires_at = entry
    if time.time() > expires_at:
        return None
    return player_id


def _prune_expired_tickets(app_state: AppState) -> None:
    now = time.time()
    expired = [t for t, (_, exp) in app_state.ws_tickets.items() if exp < now]
    for t in expired:
        app_state.ws_tickets.pop(t, None)


def _resolve_ws_ticket_requester(request: Request, app_state: AppState) -> str:
    """Identify the player requesting a WS ticket.

    Prefers `Authorization: Bearer <access_token>` (API/future non-browser
    clients); falls back to the signed `lorecraft_session` cookie (the
    browser lobby login path), since browsers can't easily attach custom
    headers to same-origin fetches without extra JS plumbing but do send
    cookies automatically.
    """
    secret = player_session_secret(app_state)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        player_id = decode_player_access_token(token, secret)
        if player_id is not None:
            return player_id
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    cookie_token = request.cookies.get(PLAYER_SESSION_COOKIE)
    if cookie_token:
        player_id = decode_player_id(cookie_token, secret)
        if player_id is not None:
            return player_id

    raise HTTPException(status_code=401, detail="No active session")


@router.post("/ws-ticket")
async def get_ws_ticket(request: Request) -> dict[str, str]:
    app_state = get_app_state(request)
    if app_state is None:
        raise HTTPException(status_code=500, detail="Server not ready")
    player_id = _resolve_ws_ticket_requester(request, app_state)
    return {"ws_ticket": issue_ws_ticket(app_state, player_id)}


# ---------------------------------------------------------------------------
# Router: POST /auth/login (JSON API)
# ---------------------------------------------------------------------------


class LoginBody(BaseModel):
    username: str
    password: str


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


# ---------------------------------------------------------------------------
# Router: POST /auth/refresh
# ---------------------------------------------------------------------------


class RefreshBody(BaseModel):
    refresh_token: str


@router.post("/refresh")
async def refresh(body: RefreshBody, request: Request) -> dict[str, object]:
    """Exchange a refresh token for a new access+refresh pair (rotation).

    Like `admin.auth`'s `/admin/auth/refresh`, rotation here means a new
    refresh token is issued on every use — there's no server-side token
    blocklist, so the old refresh token remains cryptographically valid
    until its own expiry rather than being immediately revoked. Consistent
    with the rest of the codebase's stateless-JWT approach.
    """
    app_state = get_app_state(request)
    if app_state is None:
        raise HTTPException(status_code=500, detail="Server not ready")
    secret = player_session_secret(app_state)

    try:
        payload = decode_token(body.refresh_token, secret)
    except jwt.InvalidTokenError as e:
        log.error("player_refresh_token_decode_failed: %s", str(e))
        raise HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        ) from e
    if payload.token_type != "refresh":
        raise HTTPException(status_code=401, detail="Expected refresh token")

    player_id = payload.username
    game_engine, _ = get_engines(request)
    with DBSession(game_engine) as db:
        if PlayerRepo(db).get(player_id) is None:
            raise HTTPException(status_code=401, detail="Player not found")

    access_ttl = app_state.settings.player_access_token_ttl_seconds
    refresh_ttl = app_state.settings.player_refresh_token_ttl_seconds
    return {
        "access_token": issue_access_token(player_id, secret, access_ttl),
        "refresh_token": issue_refresh_token(player_id, secret, refresh_ttl),
        "token_type": "bearer",
        "expires_in": access_ttl,
        "player_id": player_id,
    }


# ---------------------------------------------------------------------------
# OAuth extensibility hook (Sprint 4.7)
# ---------------------------------------------------------------------------
#
# PlayerAuth.provider/provider_subject already generalize beyond "local":
# provider="google", provider_subject=<google_sub> works with the exact same
# table shape (see docs/player_authentication.md). This stub marks where a
# real provider integration plugs in — exchanging an authorization code for
# an ID token, verifying it, and looking up/creating a PlayerAuth row by
# (provider, provider_subject) — without pretending to implement it, since
# that needs a registered OAuth client (client id/secret, redirect URI) this
# LAN-party engine doesn't have configured. Not wired into any client.


@router.post("/oauth/{provider}/callback")
async def oauth_callback(provider: str) -> None:
    """Extension point for a future OAuth provider (e.g. `google`).

    Deliberately unimplemented: raises 501 rather than silently accepting
    requests it can't actually authenticate. See module docstring above.
    """
    raise HTTPException(
        status_code=501,
        detail=f"OAuth provider '{provider}' is not configured on this server.",
    )
