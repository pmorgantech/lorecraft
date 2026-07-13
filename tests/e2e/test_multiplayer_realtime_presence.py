"""Browser e2e tests for multiplayer presence roster updates (Sprint 50, Priority 1).

Split from test_multiplayer_realtime.py (2026-07-13) for xdist file-level
parallelism. Both players start in Village Square of Ashmoore (a fresh
live_server per test); after each test both browser contexts are torn down
by the fixtures.

What the server actually broadcasts (engine/game/broadcast.py, main.py /ws):
- WS connect → `player_joined`; disconnect/leave → `player_left` / `state_change`
  — both drive refreshPlayersOnline() on receivers.

Note: `#player-count` is server-rendered and NOT updated by the WS handlers
(only the `#players-online` list is refreshed), and `village_square` always
contains the unconditional `player-2` seed body — so these tests assert on
*usernames appearing/disappearing in `#players-online`*, not on the count.
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


def test_player_joined_updates_here_now(
    page: Any, second_page: Any, live_server: str
) -> None:
    """P1.2: a player joining the room appears in existing occupants' "Here Now".

    B is in Village Square and connected. A logs in / connects into the same
    room; A's username shows up in B's #players-online via the `player_joined`
    push — without B doing anything.
    """
    username_a, username_b = _names()

    # B enters first and is fully connected.
    create_character(second_page, live_server, username_b)
    wait_for_ws_connected(second_page)

    # A is not present yet (A hasn't been created).
    assert username_a not in second_page.locator("#players-online").inner_text()

    # A joins the same room.
    create_character(page, live_server, username_a)
    wait_for_ws_connected(page)

    # B's roster updates to include A, pushed via player_joined (no B action).
    second_page.locator("#players-online", has_text=username_a).wait_for()


def test_player_left_decrements_the_panel(
    page: Any, second_page: Any, live_server: str
) -> None:
    """P1.3: when a player leaves the room they disappear from "Here Now".

    A and B both in Village Square. A: `go east`. A's name disappears from B's
    #players-online (state_change to the room A left) and B's feed gains the
    "leaves" narration.
    """
    username_a, username_b = _names()

    create_character(page, live_server, username_a)
    create_character(second_page, live_server, username_b)
    wait_for_ws_connected(page)
    wait_for_ws_connected(second_page)

    # B sees A in the room to start with.
    second_page.locator("#players-online", has_text=username_a).wait_for()

    # A leaves east.
    send_command(page, "go east")
    page.locator("#room-description", has_text="Market Stalls").wait_for()

    # B's roster loses A (async refresh → wait on B's DOM).
    second_page.wait_for_function(
        "name => !document.querySelector('#players-online').textContent.includes(name)",
        arg=username_a,
    )
    # And B sees A's departure narrated in the feed.
    second_page.locator("#feed", has_text=username_a).wait_for()
