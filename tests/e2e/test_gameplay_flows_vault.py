"""Browser e2e test for the locked vault door → key golden path.

Split from test_gameplay_flows.py (2026-07-13) for xdist file-level
parallelism -- see docs/roadmap.md's playtesting section for the golden path
this suite drives (Ashmoore dev world) through a real browser against a real
live server, to catch regressions ASGI-transport integration tests can't see
(HTMX swaps, OOB updates, WebSocket-driven panels).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.e2e._helpers import create_character, navigate_to_vault_hall, send_command

pytestmark = pytest.mark.e2e


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
