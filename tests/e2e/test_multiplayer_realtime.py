"""Browser end-to-end tests for multiplayer/WebSocket paths (Sprint 50, Priority 1).

These tests exercise the entire WS broadcast layer — the core gap in the existing
e2e suite. Both players start in Village Square of Ashmoore (a fresh live_server
per test); after each test both browser contexts are torn down by the fixtures.

Pattern (see _helpers.py module docstring):
- The *receiver* must be WS-connected before the *actor* triggers a room
  broadcast, or the push reaches nobody — always wait_for_ws_connected() first.
- WS pushes are async: assert on the receiver's DOM via wait_for_*, never a bare
  assert right after the actor's command.

What the server actually broadcasts (engine/game/broadcast.py, main.py /ws):
- `say`/room narration → `feed_append` (type room_event / chat) to other room
  occupants; the actor is excluded and gets their own line via command_result.
- movement / take / drop → a `state_change` nudge listing affected panels
  (room-description, inventory, players-online, minimap); receivers re-fetch
  those partials over HTMX.
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

from tests.e2e._helpers import (
    create_character,
    send_command,
    wait_for_ws_connected,
)

pytestmark = pytest.mark.e2e


def _names() -> tuple[str, str]:
    return (
        f"e2e_a_{uuid.uuid4().hex[:8]}",
        f"e2e_b_{uuid.uuid4().hex[:8]}",
    )


def test_say_propagates_to_another_player_in_room(
    page: Any, second_page: Any, live_server: str
) -> None:
    """P1.1: one player's `say` reaches the other player's feed via WS broadcast.

    Why e2e: exercises the full WS push path; ASGI-transport integration tests
    can't open the socket. This is the canonical multiplayer test.
    """
    username_a, username_b = _names()

    create_character(page, live_server, username_a)
    create_character(second_page, live_server, username_b)
    # Both connected before A broadcasts, or B misses the push.
    wait_for_ws_connected(page)
    wait_for_ws_connected(second_page)

    send_command(page, "say hello there")

    # B's feed gains the message (async broadcast → wait on B's DOM).
    second_page.locator(
        "#feed", has_text=f'{username_a} says: "hello there"'
    ).wait_for()


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


def test_observer_sees_third_person_narration_form(
    page: Any, second_page: Any, live_server: str
) -> None:
    """P1.5: the observer sees the third-person narration; the actor does not.

    Closes the other half of the 2026-07-04 actor-only split bug. A takes the
    coin: A's feed shows "You take"; B's feed shows "<A> takes ..."; and A's
    feed does NOT contain that third-person line. Pairs with
    test_actor_only_sees_own_message_not_room_narration (item-actions file).
    """
    username_a, username_b = _names()

    create_character(page, live_server, username_a)
    create_character(second_page, live_server, username_b)
    wait_for_ws_connected(page)
    wait_for_ws_connected(second_page)

    send_command(page, "take coin")

    # A sees the first-person actor form.
    page.locator("#feed", has_text="You take").wait_for()

    # B sees the third-person form "<A> takes ...".
    second_page.locator("#feed", has_text=f"{username_a} takes").wait_for()

    # A must NOT see the third-person form (the split's actor side).
    a_feed = page.locator("#feed").inner_text()
    assert f"{username_a} takes" not in a_feed, (
        f"Actor should not see third-person narration. Feed was:\n{a_feed}"
    )
