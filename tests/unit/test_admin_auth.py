"""Unit tests for admin JWT auth and password hashing."""

import pytest

from lorecraft.admin.auth import (
    ROLE_LEVELS,
    create_token,
    decode_token,
    has_role,
    hash_password,
    verify_password,
)

_SECRET = "test-secret-32-chars-long-enough!"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_hash_password_is_verifiable() -> None:
    stored = hash_password("hunter2")
    assert verify_password("hunter2", stored)


def test_wrong_password_is_rejected() -> None:
    stored = hash_password("hunter2")
    assert not verify_password("wrong", stored)


def test_two_hashes_of_same_password_differ() -> None:
    a = hash_password("same")
    b = hash_password("same")
    assert a != b  # different salts


def test_malformed_hash_returns_false() -> None:
    assert not verify_password("anything", "no-colon-here")


# ---------------------------------------------------------------------------
# JWT creation and decoding
# ---------------------------------------------------------------------------


def test_access_token_round_trip() -> None:
    token = create_token("alice", "superadmin", _SECRET, 900, "access")
    payload = decode_token(token, _SECRET)
    assert payload.username == "alice"
    assert payload.role == "superadmin"
    assert payload.token_type == "access"


def test_refresh_token_type() -> None:
    token = create_token("bob", "observer", _SECRET, 28800, "refresh")
    payload = decode_token(token, _SECRET)
    assert payload.token_type == "refresh"


def test_expired_token_raises() -> None:
    import jwt

    token = create_token(
        "alice", "observer", _SECRET, ttl_seconds=-1, token_type="access"
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token, _SECRET)


def test_wrong_secret_raises() -> None:
    import jwt

    token = create_token("alice", "observer", _SECRET, 900, "access")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, "wrong-secret")


def test_tampered_token_raises() -> None:
    import jwt

    token = create_token("alice", "superadmin", _SECRET, 900, "access")
    tampered = token[:-4] + "xxxx"
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(tampered, _SECRET)


# ---------------------------------------------------------------------------
# Role hierarchy
# ---------------------------------------------------------------------------


def test_role_levels_are_ordered() -> None:
    assert ROLE_LEVELS["observer"] < ROLE_LEVELS["moderator"]
    assert ROLE_LEVELS["moderator"] < ROLE_LEVELS["world-builder"]
    assert ROLE_LEVELS["world-builder"] < ROLE_LEVELS["superadmin"]


def test_has_role_same_level() -> None:
    assert has_role("superadmin", "superadmin")
    assert has_role("observer", "observer")


def test_has_role_higher_satisfies_lower() -> None:
    assert has_role("superadmin", "observer")
    assert has_role("world-builder", "moderator")


def test_has_role_lower_does_not_satisfy_higher() -> None:
    assert not has_role("observer", "moderator")
    assert not has_role("moderator", "superadmin")


def test_has_role_unknown_role_fails() -> None:
    assert not has_role("unknown", "observer")
