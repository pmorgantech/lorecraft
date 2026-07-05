"""Unit tests for signed player session tokens."""

from __future__ import annotations

from lorecraft.webui.admin.auth import create_token
from lorecraft.webui.player.player_auth import create_player_token, decode_player_id

_SECRET = "test-secret-32-chars-long-enough!"
_OTHER_SECRET = "a-completely-different-secret!!"


def test_round_trip_returns_player_id() -> None:
    token = create_player_token("player-42", _SECRET, ttl_seconds=3600)
    assert decode_player_id(token, _SECRET) == "player-42"


def test_wrong_secret_is_rejected() -> None:
    token = create_player_token("player-42", _SECRET, ttl_seconds=3600)
    assert decode_player_id(token, _OTHER_SECRET) is None


def test_garbage_token_is_rejected() -> None:
    assert decode_player_id("not-a-jwt", _SECRET) is None


def test_expired_token_is_rejected() -> None:
    token = create_player_token("player-42", _SECRET, ttl_seconds=-1)
    assert decode_player_id(token, _SECRET) is None


def test_admin_token_cannot_be_used_as_player_token() -> None:
    """Even with the same secret, an admin-issued token must not resolve as a player."""
    admin_token = create_token(
        "player-42", "superadmin", _SECRET, ttl_seconds=3600, token_type="access"
    )
    assert decode_player_id(admin_token, _SECRET) is None
