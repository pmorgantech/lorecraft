"""Browser e2e tests for session persistence & unauthenticated access
(Sprint 50, Priority 2).

Split from test_auth_flows.py (2026-07-13) for xdist file-level
parallelism. Exercises session persistence across a reload and
unauthenticated access to /game.

Observed server behavior (frontend.py):
- Unauthenticated `/game` raises **401** ("No active session") because the
  test server leaves `allow_query_player_id` at its Settings default (False).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest

from tests.e2e._helpers import create_character

pytestmark = pytest.mark.e2e


def test_session_persists_across_reload(page: Any, live_server: str) -> None:
    """P2.4: the signed session cookie keeps the player in /game across a reload."""
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)
    page.locator("#room-description", has_text="Village Square of Ashmoore").wait_for()

    page.reload()

    # Still authenticated in /game as the same character.
    assert re.search(r"/game$", page.url)
    page.locator("#room-description", has_text="Village Square of Ashmoore").wait_for()
    assert username in page.locator("body").inner_text()


def test_unauthenticated_game_is_refused(new_page: Any, live_server: str) -> None:
    """P2.5: hitting /game with no session does not grant access.

    Current behavior is a raw 401 ("No active session") from get_current_player
    (the test server keeps allow_query_player_id=False). The essential property
    is that the game UI is never rendered for an unauthenticated request.
    """
    page = new_page()
    response = page.goto(f"{live_server}/game")

    assert response is not None
    assert response.status == 401
    # The game UI never renders.
    assert page.locator("#command-input").count() == 0
