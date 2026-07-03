"""Browser end-to-end tests for the HTMX/Alpine game UI.

Drives the golden path documented in docs/roadmap.md's playtesting section
(Ashmoore dev world) through a real browser against a real live server, to
catch regressions that ASGI-transport integration tests can't see (HTMX
swaps, OOB updates, WebSocket-driven panels).
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
    page.click("text=Create & Enter")
    page.wait_for_url(re.compile(r".*/game$"))


def _send_command(page: Any, command: str) -> None:
    """Submit a command and wait for the HTMX round-trip to finish.

    handleCommandSuccess() clears #command-input only after the /command
    response has been swapped in, so polling for an empty value is a
    reliable, app-specific "request settled" signal.
    """
    page.fill("#command-input", command)
    page.click("#command-form button[type=submit]")
    page.wait_for_function("document.getElementById('command-input').value === ''")


def test_new_character_starts_in_village_square(page: Any, live_server: str) -> None:
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    _create_character(page, live_server, username)

    page.locator("#room-description", has_text="Village Square of Ashmoore").wait_for()


def test_move_and_take_item_updates_room_and_inventory(
    page: Any, live_server: str
) -> None:
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    _create_character(page, live_server, username)

    _send_command(page, "go east")
    page.locator("#room-description", has_text="Market Stalls").wait_for()

    _send_command(page, "take coin")
    page.locator("#inventory", has_text="Worn Copper Coin").wait_for()


def test_dialogue_choice_starts_quest(page: Any, live_server: str) -> None:
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    _create_character(page, live_server, username)

    _send_command(page, "go west")
    page.locator("#room-description", has_text="Wandering Crow Inn").wait_for()

    _send_command(page, "talk mira")
    dialogue_overlay = page.locator("#dialogue-overlay")
    dialogue_overlay.wait_for()
    assert "Any news around town?" in dialogue_overlay.inner_text()

    dialogue_overlay.get_by_text("Any news around town?").click()
    page.locator("#dialogue-overlay", has_text="I'll look into it.").wait_for()

    page.locator("#quest-tracker", has_text="Lights in the Square").wait_for()
