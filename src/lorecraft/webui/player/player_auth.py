"""Player session cookie authentication for the HTMX/lobby web client.

Reuses the JWT primitives from `lorecraft.webui.admin.auth` but signs with a
separate secret (`Settings.player_session_secret`) and a distinct
`token_type`, so a player session token can never be replayed as an admin
token even if secrets were ever mixed up.
"""

from __future__ import annotations

import logging

import jwt

from lorecraft.webui.admin.auth import create_token, decode_token

log = logging.getLogger(__name__)

PLAYER_SESSION_COOKIE = "lorecraft_session"
_TOKEN_TYPE = "player"
_ROLE = "player"


def create_player_token(player_id: str, secret: str, ttl_seconds: int) -> str:
    return create_token(player_id, _ROLE, secret, ttl_seconds, _TOKEN_TYPE)


def decode_player_id(token: str, secret: str) -> str | None:
    """Return the player id encoded in `token`, or None if invalid/expired/wrong type."""
    try:
        payload = decode_token(token, secret)
    except jwt.InvalidTokenError as e:
        log.error("player_token_decode_failed: %s", str(e))
        return None
    if payload.token_type != _TOKEN_TYPE:
        return None
    return payload.username
