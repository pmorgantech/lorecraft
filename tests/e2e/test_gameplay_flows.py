"""Browser end-to-end tests for the HTMX/Alpine game UI.

Drives the golden path documented in docs/roadmap.md's playtesting section
(Ashmoore dev world) through a real browser against a real live server, to
catch regressions that ASGI-transport integration tests can't see (HTMX
swaps, OOB updates, WebSocket-driven panels).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.e2e._helpers import (
    create_character,
    navigate_to_vault_hall,
    send_command,
    send_command_via_enter,
)

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


def test_help_output_preserves_line_breaks(page: Any, live_server: str) -> None:
    """Regression test (2026-07-04): `help`'s multi-line output (joined with
    "\\n") rendered as one giant wrapped paragraph, because the feed message
    span had no whitespace styling and browsers collapse literal newlines by
    default. The message span must preserve them (whitespace-pre-line)."""
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    # `help commands` is the multi-line grouped list (bare `help` is now a short
    # curated set); either way the span must preserve newlines.
    send_command(page, "help commands")

    message_span = page.locator("#feed .msg", has_text="All commands").locator(
        "span.whitespace-pre-line"
    )
    message_span.wait_for()
    white_space = message_span.evaluate("el => getComputedStyle(el).whiteSpace")
    assert white_space == "pre-line"


def test_new_character_starts_in_village_square(page: Any, live_server: str) -> None:
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    page.locator("#room-description", has_text="Village Square of Ashmoore").wait_for()


def test_move_and_take_item_updates_room_and_inventory(
    page: Any, live_server: str
) -> None:
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    send_command(page, "go east")
    page.locator("#room-description", has_text="Market Stalls").wait_for()

    send_command(page, "take coin")
    page.locator("#inventory", has_text="Worn Copper Coin").wait_for()


def test_dialogue_choice_starts_quest(page: Any, live_server: str) -> None:
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    send_command(page, "go west")
    page.locator("#room-description", has_text="Wandering Crow Inn").wait_for()

    send_command(page, "talk mira")
    dialogue_overlay = page.locator("#dialogue-overlay")
    dialogue_overlay.wait_for()
    assert "Any news around town?" in dialogue_overlay.inner_text()

    dialogue_overlay.get_by_text("Any news around town?").click()
    page.locator("#dialogue-overlay", has_text="I'll look into it.").wait_for()

    # The Standard layout's right column is a single Inv/Quests/Stats tabbed
    # pane (Sprint 62 rebuild) — #quest-tracker exists but stays x-show-hidden
    # until its tab is active.
    page.click("button[role='tab']:has-text('Quests')")
    page.locator("#quest-tracker", has_text="Lights in the Square").wait_for()


# ---------------------------------------------------------------------------
# Priority 3 (Sprint 50) — interaction flows touching real JS/Alpine
# ---------------------------------------------------------------------------


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


def test_full_dialogue_traversal_then_dismiss(page: Any, live_server: str) -> None:
    """P3.2: traverse a multi-choice dialogue branch, then dismiss it.

    The existing dialogue test clicks exactly one choice. This walks Mira's
    greeting → town_news branch (two choice nodes) and then closes via the
    "End conversation" button, asserting the overlay is present during and
    hidden after dismissal.
    """
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    send_command(page, "go west")
    page.locator("#room-description", has_text="Wandering Crow Inn").wait_for()

    send_command(page, "talk mira")
    overlay = page.locator("#dialogue-overlay")
    overlay.wait_for(state="visible")
    # Greeting node offers multiple choices.
    assert "Any news around town?" in overlay.inner_text()
    assert "Nothing, thanks." in overlay.inner_text()

    # Advance to the town_news node (a second choice branch).
    overlay.get_by_text("Any news around town?").click()
    page.locator(
        "#dialogue-overlay", has_text="Strange lights have been seen"
    ).wait_for()

    # Dismiss via the End conversation button; the overlay closes.
    overlay.get_by_text("End conversation").click()
    overlay.wait_for(state="hidden")


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


def test_locked_door_key_golden_path(page: Any, live_server: str) -> None:
    """P3.3: the locked vault door → key golden path (multi-step regression anchor).

    The vault hall's east exit is locked with `key_item_id: good_key`, and the
    hall holds a matching **Good Key** and a non-matching **Bad Key**. Verifies
    the full lock mechanic through the real UI:
      - without a key the way is locked,
      - the Bad Key is rejected ("not the right key"),
      - the Good Key unlocks it, and you pass through into the Inner Vault.
    """
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)
    navigate_to_vault_hall(page)

    # Locked with no key.
    send_command(page, "go east")
    page.locator("#feed", has_text="The way is locked").wait_for()
    page.locator("#room-description", has_text="Vault Hall").wait_for()

    # The Bad Key is the wrong key.
    send_command(page, "take bad key")
    page.locator("#inventory", has_text="Bad Key").wait_for()
    send_command(page, "unlock east")
    page.locator("#feed", has_text="You don't have the right key").wait_for()

    # The Good Key unlocks the door.
    send_command(page, "take good key")
    page.locator("#inventory", has_text="Good Key").wait_for()
    send_command(page, "unlock east")
    page.locator("#feed", has_text="You unlock the way east").wait_for()

    # And now you can pass through into the inner vault.
    send_command(page, "go east")
    page.locator("#room-description", has_text="Inner Vault").wait_for()
