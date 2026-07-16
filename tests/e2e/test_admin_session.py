"""Browser e2e: the admin console auto-logs-out on a stale/invalid session.

Drives the real admin console (`/admin`) in a headless browser against a live
uvicorn server seeded with an admin user. Verifies that when the access token
goes stale, the UI returns to the login screen (clearing the WS + token) instead
of leaving a dead session in place behind a transient "session expired" toast.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.conftest import admin_login

pytestmark = pytest.mark.e2e


def test_stale_token_http_401_forces_logout(page: Any, admin_server: str) -> None:
    admin_login(page, admin_server)
    page.click('.category-tab[data-category="system"]')
    page.wait_for_selector("#tab-system", state="visible")
    page.wait_for_selector("#sys-health-tbody tr")

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
    admin_login(page, admin_server)

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
