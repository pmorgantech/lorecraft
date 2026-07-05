"""Unit tests for the configurable password complexity policy (wishlist.md —
Player Creation)."""

from __future__ import annotations

from lorecraft.config import Settings
from lorecraft.webui.player.password_policy import PasswordPolicy, validate_password

DEFAULT = PasswordPolicy()  # min 8/max 32, mixed-case + number required, no symbol


def test_default_policy_matches_wishlist_defaults() -> None:
    assert DEFAULT.min_length == 8
    assert DEFAULT.max_length == 32
    assert DEFAULT.require_mixed_case is True
    assert DEFAULT.require_number is True
    assert DEFAULT.require_symbol is False


def test_valid_password_has_no_failures() -> None:
    assert validate_password("Hunter2pw", DEFAULT) == []


def test_too_short_is_rejected() -> None:
    failures = validate_password("Ab3", DEFAULT)
    assert any("at least 8" in f for f in failures)


def test_too_long_is_rejected() -> None:
    policy = PasswordPolicy(max_length=10)
    failures = validate_password("Abcdef12345", policy)  # 11 chars
    assert any("at most 10" in f for f in failures)


def test_missing_mixed_case_is_rejected() -> None:
    failures = validate_password("hunter2pw", DEFAULT)  # no uppercase
    assert any("upper- and lower-case" in f for f in failures)


def test_missing_number_is_rejected() -> None:
    failures = validate_password("HunterPass", DEFAULT)  # no digit
    assert any("number" in f for f in failures)


def test_symbol_required_when_configured() -> None:
    policy = PasswordPolicy(require_symbol=True)
    assert any("symbol" in f for f in validate_password("Hunter2pw", policy))
    assert validate_password("Hunter2pw!", policy) == []


def test_symbol_not_required_by_default() -> None:
    assert validate_password("Hunter2pw", DEFAULT) == []


def test_disabled_requirements_only_enforce_length() -> None:
    policy = PasswordPolicy(
        require_mixed_case=False, require_number=False, require_symbol=False
    )
    assert validate_password("lowercaseonly", policy) == []
    assert validate_password("short", policy) != []  # still too short


def test_from_settings_reads_configured_values() -> None:
    settings = Settings(
        password_min_length=12,
        password_max_length=20,
        password_require_mixed_case=False,
        password_require_symbol=True,
        password_require_number=False,
    )
    policy = PasswordPolicy.from_settings(settings)
    assert policy.min_length == 12
    assert policy.max_length == 20
    assert policy.require_mixed_case is False
    assert policy.require_symbol is True
    assert policy.require_number is False


def test_requirements_lists_active_rules_only() -> None:
    reqs = " | ".join(DEFAULT.requirements())
    assert "8–32 characters" in reqs
    assert "upper- and lower-case" in reqs
    assert "number" in reqs
    assert "symbol" not in reqs  # not required by default
