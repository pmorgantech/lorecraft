"""Fixtures for browser end-to-end tests.

These tests drive a real browser (via Playwright) against a real, live
uvicorn server — as opposed to the ASGI-transport integration tests in
tests/integration/, which never touch a socket or render HTML/JS. Requires
`pip install -e .[e2e]` and `playwright install chromium`.
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
sync_playwright = playwright_sync_api.sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
_STARTUP_TIMEOUT_SECONDS = 10.0

# Seeded admin used by the admin-console e2e tests.
ADMIN_USER = "e2e-admin"
ADMIN_PASS = "e2e-admin-pass-1234"


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
def live_server(tmp_path: Path) -> Iterator[str]:
    """Boot the real app against a fresh, disposable sqlite DB per test."""
    settings = Settings(
        database_path=str(tmp_path / "e2e-game.db"),
        audit_database_path=str(tmp_path / "e2e-audit.db"),
        world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml"),
        seed_player_id="",
        seed_player_username="",
    )
    app = create_app(settings=settings)
    server = _LiveServer(app)
    server.start()
    try:
        yield server.base_url
    finally:
        server.stop()


@pytest.fixture
def admin_server(tmp_path: Path) -> Iterator[str]:
    """Boot the real app (fresh DB) with a seeded superadmin for admin-console tests."""
    settings = Settings(
        database_path=str(tmp_path / "e2e-game.db"),
        audit_database_path=str(tmp_path / "e2e-audit.db"),
        world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml"),
        # Point content mirrors at empty tmp files so the tracker starts clean
        # (don't bootstrap the repo's real docs/issues.yaml into the test DB).
        issues_yaml_path=str(tmp_path / "issues.yaml"),
        news_yaml_path=str(tmp_path / "news.yaml"),
        help_yaml_path=str(tmp_path / "help_topics.yaml"),
        seed_player_id="",
        seed_player_username="",
        admin_jwt_secret="e2e-admin-session-secret-key-32chars!",
        admin_seed_username=ADMIN_USER,
        admin_seed_password=ADMIN_PASS,
        admin_seed_role="superadmin",
    )
    server = _LiveServer(create_app(settings=settings))
    server.start()
    try:
        yield server.base_url
    finally:
        server.stop()


def admin_login(page: Any, base_url: str) -> None:
    """Drive the admin login form until the admin shell is visible."""
    page.goto(f"{base_url}/admin")
    page.wait_for_selector("#login-screen", state="visible")
    page.fill("#l-username", ADMIN_USER)
    page.fill("#l-password", ADMIN_PASS)
    page.click("#l-submit")
    page.wait_for_selector("#admin-screen", state="visible")


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch(headless=True)
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser: Any) -> Iterator[Any]:
    context = browser.new_context()
    new_page = context.new_page()
    yield new_page
    context.close()
