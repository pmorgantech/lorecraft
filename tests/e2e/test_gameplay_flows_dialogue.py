"""Browser e2e tests for NPC dialogue traversal (quest start + multi-choice).

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

from tests.e2e._helpers import create_character, send_command

pytestmark = pytest.mark.e2e


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
