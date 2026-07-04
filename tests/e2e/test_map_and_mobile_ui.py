"""Browser end-to-end tests for Sprint 26: full-screen map modal and the
mobile tab layout — Alpine/HTMX interactions ASGI-transport tests can't see.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest

pytestmark = pytest.mark.e2e


def _create_character(page: Any, base_url: str, username: str) -> None:
    page.goto(f"{base_url}/lobby")
    page.click("text=Create New Character")
    page.fill("#username", username)
    page.fill("#create-password", "e2e-test-password")
    page.click("text=Create & Enter")
    page.wait_for_url(re.compile(r".*/game$"))


def test_map_modal_opens_and_renders_current_room(page: Any, live_server: str) -> None:
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    _create_character(page, live_server, username)

    page.click('button[title="Full-screen map"]')

    modal_content = page.locator("#map-modal-content")
    modal_content.locator("svg").wait_for()
    assert "Village Square of Ashmoore" in modal_content.inner_text()


def test_map_modal_closes_on_escape(page: Any, live_server: str) -> None:
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    _create_character(page, live_server, username)

    page.click('button[title="Full-screen map"]')
    page.locator("#map-modal-content svg").wait_for()

    page.keyboard.press("Escape")
    page.wait_for_function(
        "document.querySelector('#map-modal-content').closest('[x-show]')"
        ".style.display === 'none' || "
        "getComputedStyle(document.querySelector('#map-modal-content')"
        ".closest('.fixed')).display === 'none'"
    )


def test_mobile_tab_bar_switches_panels(page: Any, live_server: str) -> None:
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    _create_character(page, live_server, username)
    page.set_viewport_size({"width": 390, "height": 844})

    # Feed is the default active tab.
    assert page.locator("#feed").is_visible()

    page.click("text=Room")
    page.locator("#room-description").wait_for()
    assert not page.locator("#feed").is_visible()

    page.click("text=Players")
    page.locator("#player-count").wait_for()
    assert not page.locator("#room-description").is_visible()
