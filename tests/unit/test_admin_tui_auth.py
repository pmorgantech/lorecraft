"""Unit tests for admin TUI credential/session handling."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from lorecraft.webui.admin.tui import app as tui_app


def test_saved_access_token_is_cleared_on_protected_401(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cred_path = tmp_path / "credentials.json"
    cred_path.write_text(
        json.dumps(
            {
                "base_url": "http://server.test",
                "username": "admin",
                "access_token": "stale-token",
            }
        )
    )
    monkeypatch.setattr(tui_app, "_CRED_PATH", cred_path)

    def raise_401(*args: Any, **kwargs: Any) -> None:
        raise urllib.error.HTTPError(
            url="http://server.test/admin/players",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b"{}"),
        )

    unauthorized_calls = 0

    def on_unauthorized() -> None:
        nonlocal unauthorized_calls
        unauthorized_calls += 1

    monkeypatch.setattr(urllib.request, "urlopen", raise_401)
    api = tui_app._Api(
        "http://server.test",
        access_token="stale-token",
        on_unauthorized=on_unauthorized,
    )

    response = api.get("/admin/players")

    assert response == {"error": "Unauthorized", "status": 401}
    assert api.access_token == ""
    assert unauthorized_calls == 1
    assert json.loads(cred_path.read_text()) == {
        "base_url": "http://server.test",
        "username": "admin",
    }


def test_login_401_does_not_trigger_session_expiry_callback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cred_path = tmp_path / "credentials.json"
    cred_path.write_text(json.dumps({"access_token": "stale-token"}))
    monkeypatch.setattr(tui_app, "_CRED_PATH", cred_path)

    def raise_401(*args: Any, **kwargs: Any) -> None:
        raise urllib.error.HTTPError(
            url="http://server.test/admin/auth/token",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b"{}"),
        )

    unauthorized_calls = 0

    def on_unauthorized() -> None:
        nonlocal unauthorized_calls
        unauthorized_calls += 1

    monkeypatch.setattr(urllib.request, "urlopen", raise_401)
    api = tui_app._Api(
        "http://server.test",
        access_token="stale-token",
        on_unauthorized=on_unauthorized,
    )

    response = api.post("/admin/auth/token", {"username": "admin", "password": "bad"})

    assert response == {"error": "Unauthorized", "status": 401}
    assert unauthorized_calls == 0


def test_malformed_credential_file_loads_as_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cred_path = tmp_path / "credentials.json"
    cred_path.write_text("{not json")
    monkeypatch.setattr(tui_app, "_CRED_PATH", cred_path)

    assert tui_app._load_creds() == {}
