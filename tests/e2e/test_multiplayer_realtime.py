"""Browser end-to-end tests for multiplayer/WebSocket paths (Sprint 50, Priority 1).

These tests verify the entire WS broadcast layer — the core gap in the existing
e2e suite. Both players start in Village Square of Ashmoore; after each test,
both connections are torn down by the fixture (fresh live_server per test).

Pattern reminder (see _helpers.py module docstring):
- Never bare-assert after a cross-client action.
- Always use page.wait_for_function/locator.wait_for on the **receiver's** DOM.
- Call wait_for_both_ws_connected() before testing cross-client updates.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.e2e._helpers import (
    create_character,
    send_command,
)

pytestmark = pytest.mark.e2e


def test_say_propagates_to_another_player_in_room(
    page: Any, second_page: Any, live_server: str
) -> None:
    """P1.1: One player's `say` reaches the other player's feed via WS broadcast.

    Why e2e: exercises the full WS push path; integration tests can't open
    the socket. This is the canonical multiplayer test.
    """
    username_a = f"e2e_a_{uuid.uuid4().hex[:8]}"
    username_b = f"e2e_b_{uuid.uuid4().hex[:8]}"

    # Both start in Village Square.
    create_character(page, live_server, username_a)
    create_character(second_page, live_server, username_b)

    # Both must be connected before testing cross-client updates.
    page.wait_for_timeout(300)
    second_page.wait_for_timeout(300)

    # A says something.
    send_command(page, "say hello there")

    # B's feed eventually contains the message (broadcast is async, so wait).
    second_page.wait_for_selector(f"#feed :text('{username_a} says: \"hello there\"')")


def test_player_joined_updates_here_now(
    page: Any, second_page: Any, live_server: str
) -> None:
    """P1.2: A new player joining a room increments the player-count panel
    on existing occupants.

    Steps: B in Village Square (initial count is 1). A logs in / walks into
    the square. B's #player-count increments and A's username appears in
    #players-online — via WS, without B acting.
    """
    username_b = f"e2e_b_{uuid.uuid4().hex[:8]}"
    username_a = f"e2e_a_{uuid.uuid4().hex[:8]}"

    # B enters first and waits for connection.
    create_character(second_page, live_server, username_b)
    second_page.wait_for_timeout(300)

    # Check B's initial player count (should be 1, just B).
    initial_count = second_page.locator("#player-count").inner_text()
    assert initial_count == "1", f"Expected 1 player, got {initial_count}"

    # A enters the same room.
    create_character(page, live_server, username_a)
    page.wait_for_timeout(300)

    # B's panel updates (count increments, A's name appears).
    second_page.wait_for_selector("#player-count", has_text="2")
    second_page.wait_for_selector(f"#players-online :text('{username_a}')")


def test_player_left_decrements_the_panel(
    page: Any, second_page: Any, live_server: str
) -> None:
    """P1.3: When a player leaves a room, the player-count decrements and
    their name disappears from #players-online.

    Steps: A and B both in Village Square. A: `go east` (leaves). B's
    #player-count drops and A's name disappears.
    """
    username_a = f"e2e_a_{uuid.uuid4().hex[:8]}"
    username_b = f"e2e_b_{uuid.uuid4().hex[:8]}"

    create_character(page, live_server, username_a)
    create_character(second_page, live_server, username_b)
    page.wait_for_timeout(300)
    second_page.wait_for_timeout(300)

    # Both start in Village Square (count = 2).
    second_page.wait_for_selector("#player-count", has_text="2")

    # A leaves east.
    send_command(page, "go east")
    page.locator("#room-description", has_text="Market Stalls").wait_for()

    # B sees the count drop and A's name disappear.
    second_page.wait_for_selector("#player-count", has_text="1")
    second_page.wait_for_function(
        f"!document.querySelector('#players-online')?.textContent?.includes('{username_a}')"
    )


def test_dropped_item_becomes_visible_to_other_player(
    page: Any, second_page: Any, live_server: str
) -> None:
    """P1.4: When a player drops an item, it appears in another player's
    room-description pane.

    Steps: A carries an item (take it first). A: `drop <item>`. B's
    #room-description "You notice:" gains the item via `state_change`.
    Then A: `take <item>` → B's room pane loses it again.
    """
    username_a = f"e2e_a_{uuid.uuid4().hex[:8]}"
    username_b = f"e2e_b_{uuid.uuid4().hex[:8]}"

    create_character(page, live_server, username_a)
    create_character(second_page, live_server, username_b)
    page.wait_for_timeout(300)
    second_page.wait_for_timeout(300)

    # A takes a coin from the starting room.
    send_command(page, "take coin")
    page.locator("#inventory", has_text="Worn Copper Coin").wait_for()

    # A drops it.
    send_command(page, "drop coin")

    # B sees it appear in the room description.
    second_page.wait_for_selector(
        "#room-description :text('You notice:') >> ../.. :text('Worn Copper Coin')"
    )

    # A picks it back up.
    send_command(page, "take coin")

    # B sees it disappear from the room.
    second_page.wait_for_function(
        "!document.querySelector('#room-description').textContent.includes('Worn Copper Coin')"
    )


def test_observer_sees_third_person_narration_form(
    page: Any, second_page: Any, live_server: str
) -> None:
    """P1.5: Observer sees the third-person narration, actor doesn't.

    Regression test closure for the 2026-07-04 actor-only split bug.
    Steps: A and B in a room with a takeable item. A: `take <item>`.
    Assert: A's feed shows "You take" (existing test).
    Additionally: B's feed shows the third-person "<A> takes <item>".
    And: A's feed does NOT contain B's third-person line.

    This pairs with test_actor_only_sees_own_message_not_room_narration
    (in test_ui_refresh_on_item_actions.py) to prove both sides of the split.
    """
    username_a = f"e2e_a_{uuid.uuid4().hex[:8]}"
    username_b = f"e2e_b_{uuid.uuid4().hex[:8]}"

    create_character(page, live_server, username_a)
    create_character(second_page, live_server, username_b)
    page.wait_for_timeout(300)
    second_page.wait_for_timeout(300)

    # Both in Village Square; A takes the coin.
    send_command(page, "take coin")

    # A sees only "You take" (actor form).
    page.wait_for_selector("#feed :text('You take')")
    a_feed = page.locator("#feed").inner_text()
    assert "You take" in a_feed

    # B sees the third-person form "<A> takes <coin>".
    second_page.wait_for_selector(f"#feed :text('{username_a} takes')")
    b_feed = second_page.locator("#feed").inner_text()
    assert f"{username_a} takes" in b_feed

    # Verify A's feed does NOT contain the third-person form (strict).
    third_person_lines = [
        line for line in a_feed.splitlines() if f"{username_a} takes" in line
    ]
    assert len(third_person_lines) == 0, (
        f"Actor should not see third-person narration. Got: {third_person_lines}"
    )
