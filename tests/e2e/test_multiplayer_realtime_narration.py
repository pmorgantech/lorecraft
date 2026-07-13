"""Browser e2e tests for multiplayer chat/action narration (Sprint 50, Priority 1).

Split from test_multiplayer_realtime.py (2026-07-13) for xdist file-level
parallelism. Both players start in Village Square of Ashmoore (a fresh
live_server per test); after each test both browser contexts are torn down
by the fixtures.

Pattern (see _helpers.py module docstring):
- The *receiver* must be WS-connected before the *actor* triggers a room
  broadcast, or the push reaches nobody — always wait_for_ws_connected() first.
- WS pushes are async: assert on the receiver's DOM via wait_for_*, never a bare
  assert right after the actor's command.
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
