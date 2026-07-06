"""Browser end-to-end tests for room-panel refresh on item actions.

Regression tests for two related bugs found 2026-07-04:
1. Room items list ("You notice:") not refreshing after 'get all' — the
   CURRENT LOCATION pane showed stale items while inventory was correct.
2. Actor seeing both their own action message AND the room narration —
   "You take X" and "player_name takes X" both appeared to the actor.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.e2e.conftest import create_character

pytestmark = pytest.mark.e2e


def _send_command(page: Any, command: str) -> None:
    """Submit a command and wait for the HTMX round-trip to finish."""
    page.fill("#command-input", command)
    page.click("#command-form button[type=submit]")
    page.wait_for_function("document.getElementById('command-input').value === ''")


def _go_to_locksmiths_gallery(page: Any) -> None:
    """village_square --north--> blacksmith_forge --north--> key_gallery."""
    _send_command(page, "north")
    page.locator("#room-description", has_text="Forge and Hammer").wait_for()
    _send_command(page, "north")
    page.locator("#room-description", has_text="Locksmith's Gallery").wait_for()


def test_get_all_refreshes_room_items_pane(page: Any, live_server: str) -> None:
    """Verify that 'get all' removes items from the room display."""
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)
    _go_to_locksmiths_gallery(page)

    room_pane = page.locator("#room-description")
    assert "You notice:" in room_pane.inner_text()
    assert "Key" in room_pane.inner_text()

    _send_command(page, "get all")

    feed = page.locator("#feed")
    assert "You take" in feed.inner_text()

    # CRITICAL: the room pane must no longer list the taken items.
    page.wait_for_function(
        """() => {
            const roomPane = document.querySelector('#room-description');
            return !!roomPane && !roomPane.textContent.includes('Key');
        }"""
    )
    room_text_after = room_pane.inner_text()
    assert "Key" not in room_text_after, (
        f"Room pane not updated after 'get all'. Still shows: {room_text_after}"
    )

    inventory = page.locator("#inventory")
    assert "Key" in inventory.inner_text()


def test_actor_only_sees_own_message_not_room_narration(
    page: Any, live_server: str
) -> None:
    """The actor must see only 'You take X', not the room narration too."""
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)
    _go_to_locksmiths_gallery(page)

    _send_command(page, "get cage key")

    feed_text = page.locator("#feed").inner_text()
    assert "You take" in feed_text

    # The room narration ("<username> takes Cage Key.") is for OTHER
    # occupants only -- the actor should see exactly one "take" line.
    take_lines = [
        line
        for line in feed_text.splitlines()
        if "take" in line.lower() and "Cage Key" in line
    ]
    assert len(take_lines) == 1, (
        f"Actor should see only their own 'You take' message. Got: {take_lines}"
    )
    assert "You take" in take_lines[0]
