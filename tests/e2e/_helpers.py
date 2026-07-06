"""Shared helpers for e2e browser tests.

These utilities reduce duplication across test files and ensure consistent
patterns for common operations (character creation, command submission, etc.).
"""

from __future__ import annotations

import re
from typing import Any


def create_character(page: Any, base_url: str, username: str) -> None:
    """Drive the lobby's new-character form through to /game.

    The create form gates its submit button on `formOk` = valid username +
    policy-compliant password + matching confirmation, so fill both password
    inputs with a compliant value (see the lobby template).
    """
    page.goto(f"{base_url}/lobby")
    page.click("text=Create New Character")
    page.fill("#username", username)
    page.fill("#create-password", "E2eTestPass1")
    page.fill("#create-password-confirm", "E2eTestPass1")
    page.click("text=Create & Enter")
    page.wait_for_url(re.compile(r".*/game$"))


def send_command(page: Any, command: str) -> None:
    """Submit a command and wait for the HTMX round-trip to finish.

    handleCommandSuccess() clears #command-input only after the /command
    response has been swapped in, so polling for an empty value is a
    reliable, app-specific "request settled" signal.

    Supports both button click and Enter keypress submission paths.
    """
    page.fill("#command-input", command)
    page.click("#command-form button[type=submit]")
    page.wait_for_function("document.getElementById('command-input').value === ''")


def send_command_via_enter(page: Any, command: str) -> None:
    """Submit a command via Enter key (history-recording path).

    The history mechanism (setupCommandHistory in app.js) only records on the
    input's own "Enter" keydown, not on button click. Use this variant when
    testing command history features.
    """
    page.fill("#command-input", command)
    page.press("#command-input", "Enter")
    page.wait_for_function("document.getElementById('command-input').value === ''")


def enable_separate_chat(page: Any, base_url: str) -> None:
    """Navigate to settings, enable the separate_chat preference, and return to /game.

    After enabling, the #chat-pane element is present (or becomes visible)
    for further assertions in the test.
    """
    page.goto(f"{base_url}/settings")
    page.check("input[name='separate_chat']")
    page.click("button[type='submit']")
    page.wait_for_selector("input[name='separate_chat']:checked")
    page.goto(f"{base_url}/game")
    page.wait_for_selector("#chat-pane")


def navigate_to_locksmiths_gallery(page: Any) -> None:
    """Navigate from village_square to the key_gallery via the forge.

    Path: village_square --north--> blacksmith_forge --north--> key_gallery.
    Used by item-action tests.
    """
    send_command(page, "north")
    page.locator("#room-description", has_text="Forge and Hammer").wait_for()
    send_command(page, "north")
    page.locator("#room-description", has_text="Locksmith's Gallery").wait_for()
