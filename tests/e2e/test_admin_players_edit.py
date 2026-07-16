"""Browser e2e: admin Dashboard edits player records."""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.conftest import admin_login

pytestmark = pytest.mark.e2e


def test_dashboard_can_edit_player_record(page: Any, admin_server: str) -> None:
    admin_login(page, admin_server)
    page.wait_for_selector("#players-tbody tr")

    row = page.locator("#players-tbody tr").first
    row.get_by_role("button", name="Edit").click()
    page.wait_for_selector("#player-editor-panel", state="visible")

    page.fill("#pe-username", "edited-player")
    page.fill("#pe-respawn-room", "market_stalls")
    page.check("#pe-pvp")
    page.check("#pe-ghost")
    page.fill("#pe-flags", '{"admin_note":"reviewed"}')
    page.fill("#pe-reason", "support edit")

    with page.expect_response(
        lambda resp: resp.request.method == "PATCH" and "/admin/players/" in resp.url
    ):
        page.click("#pe-save-btn")
    page.wait_for_function(
        "() => document.getElementById('pe-status').textContent.includes('Saved')"
    )

    assert page.input_value("#pe-username") == "edited-player"
    assert page.input_value("#pe-respawn-room") == "market_stalls"
    assert page.is_checked("#pe-pvp")
    assert page.is_checked("#pe-ghost")
    assert "edited-player" in page.locator("#players-tbody").inner_text()


def test_dashboard_player_tab_can_bestow_coins(page: Any, admin_server: str) -> None:
    admin_login(page, admin_server)
    page.wait_for_selector("#players-tbody tr")

    row = page.locator("#players-tbody tr").first
    row.get_by_role("button", name="Edit").click()
    page.wait_for_selector("#player-editor-panel", state="visible")

    page.fill("#pe-reason", "support stipend")
    page.fill("#pe-bestow-coins", "12")

    with page.expect_response(
        lambda resp: (
            resp.request.method == "POST"
            and "/admin/players/" in resp.url
            and resp.url.endswith("/bestow")
        )
    ):
        page.click("#pe-bestow-btn")
    page.wait_for_function(
        "() => document.getElementById('pe-status').textContent.includes('Bestowed')"
    )
