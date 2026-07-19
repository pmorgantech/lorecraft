"""Browser e2e tests for command-input UX: history recall and error handling.

Split from test_gameplay_flows.py (2026-07-13) for xdist file-level
parallelism -- see docs/project/roadmap.md's playtesting section for the golden path
this suite drives (Ashmoore dev world) through a real browser against a real
live server, to catch regressions ASGI-transport integration tests can't see
(HTMX swaps, OOB updates, WebSocket-driven panels).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.e2e._helpers import create_character, send_command, send_command_via_enter

pytestmark = pytest.mark.e2e


def test_arrow_up_history_recall_then_enter_submits(
    page: Any, live_server: str
) -> None:
    """Regression test (2026-07-04): recalling a command with ArrowUp sets the
    input's raw DOM value directly, which never fired Alpine's x-model input
    listener -- localCommand stayed stale, keeping the Send button's
    :disabled="!localCommand.trim()" true even though the field visibly
    showed recalled text, and a disabled submit control blocks the browser's
    implicit submit-on-Enter. Pressing Enter after a history recall must
    submit the command, not require clicking Send.

    History is only recorded on the input's own "Enter" keydown (see
    setupCommandHistory in app.js), not on a Send-button click, so the setup
    command below must be submitted via Enter too, matching the real
    "type, Enter, arrow up, Enter" flow that surfaced the bug."""
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    input_box = page.locator("#command-input")
    input_box.fill("look")
    input_box.press("Enter")
    page.wait_for_function("document.getElementById('command-input').value === ''")

    input_box.click()
    input_box.press("ArrowUp")
    assert input_box.input_value() == "look"

    input_box.press("Enter")
    page.wait_for_function("document.getElementById('command-input').value === ''")


def test_command_history_arrow_up_down_navigation(page: Any, live_server: str) -> None:
    """P3.1: ArrowUp/ArrowDown walk the multi-entry command history, and the
    index resets after a submit.

    The existing history test only covers a single-entry ArrowUp+Enter. This
    guards the Alpine `x-model` seam that produced the original recall bug
    across several entries and in both directions. History is recorded on the
    input's own Enter keydown (setupCommandHistory in app.js), so all setup
    commands are submitted via Enter.
    """
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    input_box = page.locator("#command-input")

    # Three distinct, read-only commands → history == [look, inventory, help].
    for command in ("look", "inventory", "help"):
        send_command_via_enter(page, command)

    input_box.click()

    # ArrowUp walks backwards from newest to oldest.
    input_box.press("ArrowUp")
    assert input_box.input_value() == "help"
    input_box.press("ArrowUp")
    assert input_box.input_value() == "inventory"
    input_box.press("ArrowUp")
    assert input_box.input_value() == "look"

    # ArrowDown walks forward again.
    input_box.press("ArrowDown")
    assert input_box.input_value() == "inventory"
    input_box.press("ArrowDown")
    assert input_box.input_value() == "help"
    # Past the newest entry, the field clears (index back to -1).
    input_box.press("ArrowDown")
    assert input_box.input_value() == ""

    # After a fresh submit the index resets: one ArrowUp shows the newest entry.
    send_command_via_enter(page, "look")
    input_box.click()
    input_box.press("ArrowUp")
    assert input_box.input_value() == "look"


def test_standard_layout_shows_vitals_near_input_and_refreshes_on_command(
    page: Any, live_server: str
) -> None:
    """The compact vitals line (previously classic-layout-only) now renders
    near the command input on every layout, including Standard (the default
    layout create_character lands on) -- and OOB-refreshes after a command,
    the same as classic already did (see docs/project/roadmap.md's vitals gap)."""
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    vitals = page.locator("#vitals")
    vitals.wait_for()
    assert "coin" in vitals.inner_text()

    send_command(page, "look")
    # Still present (OOB-swapped, not removed) after the round-trip.
    page.locator("#vitals").wait_for()
    assert "coin" in page.locator("#vitals").inner_text()


def test_invalid_command_shows_error_and_refocuses_input(
    page: Any, live_server: str
) -> None:
    """P3.4: an unparseable command shows the parser error and still clears +
    refocuses the input.

    Proves handleCommandSuccess runs even on a non-mutating/blocked response
    (the feed gains the "I don't understand" line, the input empties, and focus
    returns to it so the player can immediately retry).
    """
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    send_command(page, "asdfqwer")

    page.locator("#feed", has_text="I don't understand").wait_for()
    # Input cleared (send_command already waited on this) and refocused.
    assert page.locator("#command-input").input_value() == ""
    page.wait_for_function(
        "document.activeElement === document.getElementById('command-input')"
    )
