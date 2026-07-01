"""Unit tests for `ensure_persisted_secret` (.env-backed secret generation)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lorecraft.config import ensure_persisted_secret

_VAR = "LORECRAFT_TEST_PERSISTED_SECRET"


@pytest.fixture(autouse=True)
def _clean_env() -> None:
    os.environ.pop(_VAR, None)
    yield
    os.environ.pop(_VAR, None)


def test_generates_and_persists_when_missing(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"

    value = ensure_persisted_secret(_VAR, env_path=env_path)

    assert value
    assert env_path.read_text().strip() == f"{_VAR}={value}"
    assert os.environ[_VAR] == value


def test_reuses_existing_env_var_without_writing(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    os.environ[_VAR] = "already-set"

    value = ensure_persisted_secret(_VAR, env_path=env_path)

    assert value == "already-set"
    assert not env_path.exists()


def test_appends_to_existing_env_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OTHER_VAR=hello\n")

    value = ensure_persisted_secret(_VAR, env_path=env_path)

    content = env_path.read_text()
    assert "OTHER_VAR=hello" in content
    assert f"{_VAR}={value}" in content


def test_second_call_returns_same_persisted_value(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"

    first = ensure_persisted_secret(_VAR, env_path=env_path)
    # Simulate a fresh process: only os.environ (already set by the first call)
    # determines the outcome now, matching real startup behavior.
    second = ensure_persisted_secret(_VAR, env_path=env_path)

    assert first == second
