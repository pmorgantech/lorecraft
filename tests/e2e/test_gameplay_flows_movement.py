"""Browser e2e tests for basic movement and inventory (take) flows.

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


def test_new_character_starts_in_village_square(page: Any, live_server: str) -> None:
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    page.locator("#room-description", has_text="Village Square of Ashmoore").wait_for()


def test_move_and_take_item_updates_room_and_inventory(
    page: Any, live_server: str
) -> None:
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    send_command(page, "go east")
    page.locator("#room-description", has_text="Market Stalls").wait_for()

    send_command(page, "take coin")
    page.locator("#inventory", has_text="Worn Copper Coin").wait_for()
