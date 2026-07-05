"""Browser e2e: the admin console auto-logs-out on a stale/invalid session.

Drives the real admin console (`/admin`) in a headless browser against a live
uvicorn server seeded with an admin user. Verifies that when the access token
goes stale, the UI returns to the login screen (clearing the WS + token) instead
of leaving a dead session in place behind a transient "session expired" toast.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn

from lorecraft.config import Settings
from lorecraft.main import create_app

playwright_sync_api = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
_STARTUP_TIMEOUT_SECONDS = 10.0

_ADMIN_USER = "e2e-admin"
_ADMIN_PASS = "e2e-admin-pass-1234"


class _LiveServer:
    """Runs the real FastAPI app under uvicorn on a background thread."""

    def __init__(self, app: Any) -> None:
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        while not self._server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("live e2e server did not start in time")
            time.sleep(0.01)

    @property
    def base_url(self) -> str:
        port = self._server.servers[0].sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


@pytest.fixture
def admin_server(tmp_path: Path) -> Iterator[str]:
    """Boot the real app (fresh DB) with a seeded admin user."""
    settings = Settings(
        database_path=str(tmp_path / "e2e-game.db"),
        audit_database_path=str(tmp_path / "e2e-audit.db"),
        world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml"),
        seed_player_id="",
        seed_player_username="",
        admin_jwt_secret="e2e-admin-session-secret-key-32chars!",
        admin_seed_username=_ADMIN_USER,
        admin_seed_password=_ADMIN_PASS,
        admin_seed_role="superadmin",
    )
    server = _LiveServer(create_app(settings=settings))
    server.start()
    try:
        yield server.base_url
    finally:
        server.stop()


def _login(page: Any, base_url: str) -> None:
    page.goto(f"{base_url}/admin")
    page.wait_for_selector("#login-screen", state="visible")
    page.fill("#l-username", _ADMIN_USER)
    page.fill("#l-password", _ADMIN_PASS)
    page.click("#l-submit")
    # Successful login swaps to the admin shell.
    page.wait_for_selector("#admin-screen", state="visible")


def test_stale_token_http_401_forces_logout(page: Any, admin_server: str) -> None:
    _login(page, admin_server)

    # Corrupt the in-memory + stored token so the next authed request 401s.
    page.evaluate(
        "() => { state.accessToken = 'stale.bogus.token';"
        " sessionStorage.setItem('lc_admin_token', 'stale.bogus.token'); }"
    )
    # Trigger an authenticated request (Audit tab -> GET /admin/audit).
    page.click('.tab[data-tab="audit"]')

    # We are dropped back to the login screen with a session-expired notice,
    # and the dead token has been cleared.
    page.wait_for_selector("#login-screen", state="visible")
    page.wait_for_selector("#admin-screen", state="hidden")
    assert "expired" in page.text_content("#l-error").lower()
    assert page.evaluate("() => sessionStorage.getItem('lc_admin_token')") is None
    assert page.evaluate("() => state.accessToken") == ""


def test_ws_auth_rejection_forces_logout(page: Any, admin_server: str) -> None:
    _login(page, admin_server)

    # Reconnect the admin WebSocket with a bogus token; the server rejects it
    # (close code 1008), which must force a logout rather than reconnect-loop.
    page.evaluate(
        "() => { state.accessToken = 'stale.bogus.token';"
        " if (state.ws) { state.ws.onclose = null; state.ws.close(); }"
        " connectAdminWs(); }"
    )

    page.wait_for_selector("#login-screen", state="visible")
    page.wait_for_selector("#admin-screen", state="hidden")
    assert "expired" in page.text_content("#l-error").lower()
    assert page.evaluate("() => state.accessToken") == ""
