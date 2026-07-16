"""Browser e2e: admin console category navigation exposes contextual sub-tabs."""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.conftest import admin_login

pytestmark = pytest.mark.e2e


def test_categories_reveal_contextual_subtabs(page: Any, admin_server: str) -> None:
    page.set_viewport_size({"width": 900, "height": 500})
    admin_login(page, admin_server)

    assert page.locator('.tab[data-tab="dashboard"]').is_visible()
    assert not page.locator('.tab[data-tab="economy"]').is_visible()

    page.click('.category-tab[data-category="tuning"]')
    assert page.locator('.tab[data-tab="clock"]').is_visible()
    assert page.locator('.tab[data-tab="economy"]').is_visible()
    assert not page.locator('.tab[data-tab="dashboard"]').is_visible()

    page.click('.tab[data-tab="economy"]')
    page.wait_for_selector("#tab-economy", state="visible")
    assert "active" in (
        page.get_attribute('.category-tab[data-category="tuning"]', "class") or ""
    )
    assert "active" in (page.get_attribute('.tab[data-tab="economy"]', "class") or "")

    page.click('.category-tab[data-category="system"]')
    assert page.locator('.tab[data-tab="system"]').is_visible()
    assert page.locator('.tab[data-tab="observability"]').is_visible()
    assert page.locator('.tab[data-tab="crashes"]').is_visible()
