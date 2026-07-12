"""Browser e2e: the admin World panel's "wipe & reseed" button (Sprint 72.2).

The server-side contract (auth-gating, validate-before-wipe, response shape) is
already covered by `tests/integration/test_admin_world_reseed.py`. This file
only exercises the client-side behaviour that lives in `admin/index.html`:
confirmation-gating before the destructive call fires, and role-based
enable/disable of the button.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.conftest import admin_login

pytestmark = pytest.mark.e2e


def _open_world_tab(page: Any) -> None:
    page.click('.tab[data-tab="world"]')
    page.wait_for_selector("#w-reseed-btn", state="visible")


def test_reseed_requires_confirmation_before_calling_endpoint(
    page: Any, admin_server: str
) -> None:
    admin_login(page, admin_server)
    _open_world_tab(page)

    calls: list[str] = []
    page.route(
        "**/admin/world/reseed",
        lambda route: (calls.append(route.request.method), route.continue_()),
    )

    # No dialog handler registered: Playwright auto-dismisses confirm(),
    # exactly like a user clicking "Cancel". The destructive request must
    # never fire and the status area stays untouched.
    page.click("#w-reseed-btn")
    page.wait_for_timeout(300)
    assert calls == []
    assert page.text_content("#w-reseed-status").strip() == ""

    # Accept the confirmation this time — the request fires, the panel
    # reports the returned counts, and the room list is refreshed.
    page.once("dialog", lambda dialog: dialog.accept())
    with page.expect_response("**/admin/world/reseed"):
        page.click("#w-reseed-btn")
    page.wait_for_function(
        "() => document.getElementById('w-reseed-status').textContent.includes('Reseeded:')"
    )
    assert calls == ["POST"]
    status = page.text_content("#w-reseed-status")
    assert "rooms" in status
    assert "player(s) relocated" in status


def test_reseed_button_gated_to_superadmin_role(page: Any, admin_server: str) -> None:
    admin_login(page, admin_server)
    _open_world_tab(page)

    # The seeded e2e admin is a superadmin (see conftest.admin_server) -> enabled.
    assert page.is_enabled("#w-reseed-btn")

    # Simulate a lesser role the same way the existing stale-session e2e test
    # pokes `state` directly (tests/e2e/test_admin_session.py) — there is no
    # world-builder login fixture, so this is the lightest way to exercise the
    # client-side gate without adding a second seeded account.
    page.evaluate("() => { state.role = 'world-builder'; updateWorldDangerZoneUI(); }")
    assert not page.is_enabled("#w-reseed-btn")
    title = (page.get_attribute("#w-reseed-btn", "title") or "").lower()
    assert "superadmin" in title

    page.evaluate("() => { state.role = 'superadmin'; updateWorldDangerZoneUI(); }")
    assert page.is_enabled("#w-reseed-btn")
