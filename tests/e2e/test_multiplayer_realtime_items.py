"""Browser e2e test for cross-client item visibility (Sprint 50, Priority 1).

Split from test_multiplayer_realtime.py (2026-07-13) for xdist file-level
parallelism. Both players start in Village Square of Ashmoore (a fresh
live_server per test); after each test both browser contexts are torn down
by the fixtures.

What the server actually broadcasts (engine/game/broadcast.py, main.py /ws):
- movement / take / drop → a `state_change` nudge listing affected panels
  (room-description, inventory, players-online, minimap); receivers re-fetch
  those partials over HTMX.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.e2e._helpers import create_character, send_command, wait_for_ws_connected

pytestmark = pytest.mark.e2e


def _names() -> tuple[str, str]:
    return (
        f"e2e_a_{uuid.uuid4().hex[:8]}",
        f"e2e_b_{uuid.uuid4().hex[:8]}",
    )


def test_dropped_item_becomes_visible_to_other_player(
    page: Any, second_page: Any, live_server: str
) -> None:
    """P1.4: an item picked up / dropped by A updates B's room-description pane.

    village_square seeds a copper coin, visible to both. A takes it → it leaves
    B's room pane (state_change → room-description refresh). A drops it → it
    returns to B's room pane.
    """
    username_a, username_b = _names()

    create_character(page, live_server, username_a)
    create_character(second_page, live_server, username_b)
    wait_for_ws_connected(page)
    wait_for_ws_connected(second_page)

    # Both see the seeded coin in the room to start with.
    second_page.locator("#room-description", has_text="Worn Copper Coin").wait_for()

    # A takes it → B's room pane loses it.
    send_command(page, "take coin")
    page.locator("#inventory", has_text="Worn Copper Coin").wait_for()
    second_page.wait_for_function(
        "() => !document.querySelector('#room-description')"
        ".textContent.includes('Worn Copper Coin')"
    )

    # A drops it → B's room pane regains it.
    send_command(page, "drop coin")
    second_page.locator("#room-description", has_text="Worn Copper Coin").wait_for()
