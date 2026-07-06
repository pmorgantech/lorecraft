"""Browser end-to-end tests for panel rendering (Sprint 50, Priority 4).

Panels that update but weren't asserted as actually re-rendered:
- P4.1 the minimap re-centers/highlights on the current room after movement.
- P4.3 the feed's autoscroll + top/bottom scroll controls.

(P4.2 — equipment/wield flow — is deferred: the Ashmoore world ships no
equippable items. No item sets the definitional `Item.slot`, so `item_fits_slot`
rejects every wield/wear, and the inventory panel has no equipped state to show.
The equip-slot mechanic is unit/integration-tested; fabricating a wieldable item
solely for one e2e test would break the repo's data-driven/no-reward-hacking
rule and perturb the audit-regression golden. Reopen when Ashmoore ships an
equippable item as real content — arguably a content gap worth filling.)
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.e2e._helpers import create_character, send_command

pytestmark = pytest.mark.e2e


def test_minimap_updates_on_movement(page: Any, live_server: str) -> None:
    """P4.1: the minimap re-renders (recentered on the new current room) on move.

    The map is centered on the current room and shows its nearest known
    neighbours (build_map_data), and the command response OOB-swaps `#minimap`.
    So any real move necessarily changes the minimap's rendered geometry — this
    asserts that swap actually happens (distinct from the modal-open test, which
    only proves the full-screen map renders).
    """
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    minimap = page.locator("#minimap")
    minimap.locator("svg").wait_for()
    before = minimap.inner_html()

    send_command(page, "go east")
    page.locator("#room-description", has_text="Market Stalls").wait_for()

    # The minimap content changes to reflect the new current room.
    page.wait_for_function(
        "prev => document.querySelector('#minimap').innerHTML !== prev",
        arg=before,
    )
    # Still a rendered map (an svg), not an empty/error state.
    page.locator("#minimap svg").wait_for()


def test_feed_top_bottom_controls_and_autoscroll(page: Any, live_server: str) -> None:
    """P4.3: the feed's "↑ top" / "↓ bottom" controls move the scroll position,
    and a new message re-pins the feed to the bottom.

    Generate enough output to overflow the feed, then drive the Alpine @click
    scroll buttons and confirm the scroll position tracks. handleCommandSuccess
    scrolls to the bottom after every command, so a new message pins the feed to
    the bottom even if the player had scrolled up.
    """
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    # Overflow the feed with several long multi-line responses.
    for _ in range(5):
        send_command(page, "help commands")
    page.wait_for_function(
        "() => { const f = document.getElementById('feed');"
        " return f.scrollHeight > f.clientHeight + 40; }"
    )

    # "↑ top" scrolls the feed to the very top.
    page.get_by_text("↑ top").click()
    page.wait_for_function("() => document.getElementById('feed').scrollTop === 0")

    # "↓ bottom" scrolls back to the bottom.
    page.get_by_text("↓ bottom").click()
    page.wait_for_function(
        "() => { const f = document.getElementById('feed');"
        " return f.scrollHeight - f.scrollTop - f.clientHeight < 4; }"
    )

    # Scroll to the top, then a new message re-pins the feed to the bottom.
    page.get_by_text("↑ top").click()
    page.wait_for_function("() => document.getElementById('feed').scrollTop === 0")
    send_command(page, "look")
    page.wait_for_function(
        "() => { const f = document.getElementById('feed');"
        " return f.scrollHeight - f.scrollTop - f.clientHeight < 40; }"
    )
