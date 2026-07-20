"""Browser e2e: admin World tab item definition editor."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from tests.e2e.conftest import admin_login

pytestmark = pytest.mark.e2e


def _open_items_tab(page: Any, admin_server: str) -> None:
    admin_login(page, admin_server)
    page.click('.category-tab[data-category="world"]')
    page.click('.tab[data-tab="items"]')
    page.wait_for_selector("#item-new-btn", state="visible")


def test_world_tab_can_create_item_definition(page: Any, admin_server: str) -> None:
    _open_items_tab(page, admin_server)
    item_id = f"e2e_admin_item_{uuid4().hex[:8]}"

    page.click("#item-new-btn")
    page.wait_for_selector("#item-editor-panel", state="visible")
    page.fill("#i-id", item_id)
    page.fill("#i-name", "E2E Admin Lantern")
    page.fill("#i-desc", "Created by the admin item editor e2e test.")
    page.fill("#i-value", "9")
    page.fill("#i-category", "supplies")

    with page.expect_response(
        lambda resp: (
            resp.request.method == "POST" and resp.url.endswith("/admin/world/items")
        )
    ):
        page.click("#item-save-btn")

    page.wait_for_function(
        """itemId => [...document.querySelectorAll("#items-tbody tr")]
          .some(row => row.textContent.includes(itemId))""",
        arg=item_id,
    )
    assert item_id in page.locator("#items-tbody").inner_text()
    assert not page.locator("#item-editor-panel").is_visible()


def test_item_editor_controls_require_world_builder_role(
    page: Any, admin_server: str
) -> None:
    _open_items_tab(page, admin_server)
    assert page.is_enabled("#item-new-btn")

    page.evaluate("() => { state.role = 'observer'; updateItemEditorUI(); }")
    assert not page.is_enabled("#item-new-btn")
    title = (page.get_attribute("#item-new-btn", "title") or "").lower()
    assert "world-builder" in title

    page.evaluate("() => { state.role = 'world-builder'; updateItemEditorUI(); }")
    assert page.is_enabled("#item-new-btn")
