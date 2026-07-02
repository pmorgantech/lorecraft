"""Tests for the GameError exception hierarchy."""

from lorecraft.errors import (
    ConflictError,
    GameError,
    NotFoundError,
    PermissionError,
    ValidationError,
)


def test_game_error_base() -> None:
    """GameError with custom code."""
    err = GameError("test message", "test_code")
    assert err.message == "test message"
    assert err.code == "test_code"
    assert str(err) == "test_code: test message"


def test_game_error_default_code() -> None:
    """GameError with default code."""
    err = GameError("test message")
    assert err.code == "unknown_error"
    assert str(err) == "unknown_error: test message"


def test_validation_error_default_code() -> None:
    """ValidationError has validation_failed default code."""
    err = ValidationError("invalid input")
    assert err.code == "validation_failed"
    assert isinstance(err, GameError)


def test_validation_error_custom_code() -> None:
    """ValidationError with custom code."""
    err = ValidationError("invalid format", "validation_bad_format")
    assert err.code == "validation_bad_format"


def test_not_found_error_default_code() -> None:
    """NotFoundError has not_found default code."""
    err = NotFoundError("player not found")
    assert err.code == "not_found"
    assert isinstance(err, GameError)


def test_not_found_error_custom_code() -> None:
    """NotFoundError with custom code."""
    err = NotFoundError("item not found", "not_found_item")
    assert err.code == "not_found_item"


def test_permission_error_default_code() -> None:
    """PermissionError has permission_denied default code."""
    err = PermissionError("access denied")
    assert err.code == "permission_denied"
    assert isinstance(err, GameError)


def test_conflict_error_default_code() -> None:
    """ConflictError has conflict default code."""
    err = ConflictError("concurrent modification")
    assert err.code == "conflict"
    assert isinstance(err, GameError)


def test_conflict_error_custom_code() -> None:
    """ConflictError with custom code."""
    err = ConflictError("race condition", "conflict_race")
    assert err.code == "conflict_race"


def test_error_hierarchy() -> None:
    """All custom errors inherit from GameError."""
    errors = [
        ValidationError("msg"),
        NotFoundError("msg"),
        PermissionError("msg"),
        ConflictError("msg"),
    ]
    for err in errors:
        assert isinstance(err, GameError)
