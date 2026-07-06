"""Browser end-to-end tests for auth & session lifecycle (Sprint 50, Priority 2).

Only the create-and-enter happy path was covered before this. These exercise
the real security surface of the lobby: logging in to an existing character,
rejecting a wrong password, refusing to silently create an account for an
unknown username, session persistence across reload, and unauthenticated
access to /game.

Observed server behavior (frontend.py):
- A failed lobby login (`POST /lobby/enter`) re-renders `lobby.html` with an
  inline `[role=alert]` error and HTTP **400** — not 401/404. (The JSON
  `/auth/*` API uses those codes; the browser form path does not.) So these
  tests assert the security-relevant *observable* outcome — the user stays on
  the lobby and never reaches /game — rather than a specific status code.
- Unauthenticated `/game` raises **401** ("No active session") because the
  test server leaves `allow_query_player_id` at its Settings default (False).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest

from tests.e2e._helpers import CHARACTER_PASSWORD, create_character, login_character

pytestmark = pytest.mark.e2e


def test_login_to_existing_character_via_login_tab(
    page: Any, new_page: Any, live_server: str
) -> None:
    """P2.1: an existing character can log back in through the Log In tab.

    Create a character (which also logs in), then in a *fresh* context use the
    default Log In tab to re-authenticate and land back in /game as the same
    character (same start room, same name).
    """
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)
    page.locator("#room-description", has_text="Village Square of Ashmoore").wait_for()

    # Fresh context: no session cookie carried over from the create flow.
    returning = new_page()
    login_character(returning, live_server, username)

    # Same character, same start room.
    returning.locator(
        "#room-description", has_text="Village Square of Ashmoore"
    ).wait_for()
    assert username in returning.locator("body").inner_text()


def test_wrong_password_is_rejected(page: Any, new_page: Any, live_server: str) -> None:
    """P2.2: a wrong password keeps the user out of the game.

    Guards the InvalidCredentialsError branch in enter_world. The user stays on
    the lobby with an error and never reaches /game.
    """
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    attacker = new_page()
    attacker.goto(f"{live_server}/lobby")
    attacker.fill("#enter-username", username)
    attacker.fill("#enter-password", "WrongPassword9")
    attacker.click("form[action='/lobby/enter'] button[type=submit]")

    # Stays on the lobby (never /game); an error alert is shown.
    attacker.locator("[role=alert]").wait_for()
    assert not re.search(r"/game$", attacker.url)
    assert attacker.locator("#command-input").count() == 0


def test_unknown_username_does_not_silently_create_account(
    new_page: Any, live_server: str
) -> None:
    """P2.3: logging in with a never-created username does NOT spawn an account.

    enter_world uses allow_create=False specifically so a typo'd name is
    rejected rather than creating an empty character. The user stays on the
    lobby and never reaches /game.
    """
    page = new_page()
    page.goto(f"{live_server}/lobby")
    page.fill("#enter-username", f"never_{uuid.uuid4().hex[:8]}")
    page.fill("#enter-password", CHARACTER_PASSWORD)
    page.click("form[action='/lobby/enter'] button[type=submit]")

    page.locator("[role=alert]").wait_for()
    assert not re.search(r"/game$", page.url)
    assert page.locator("#command-input").count() == 0


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
