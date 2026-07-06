"""Browser end-to-end test for WS reconnect (Sprint 50, Priority 5).

Verifies the marquee reconnect value: after a genuine socket drop, the client
auto-reconnects (app.js onclose backoff) and **resumes receiving live room
broadcasts**. Kept isolated with generous timeouts, as the plan flagged.

Two important findings from building this (documented so it isn't relitigated):

1. **Playwright `context.set_offline(True)` does not sever an already-open
   WebSocket** in this Chromium — `isConnected()` stays true through the whole
   offline window and a "missed" message is delivered live over the still-open
   socket (a false positive). So a real drop is forced via the app.js debug hook
   `window.Lorecraft.debugDropSocket()` (see `drop_ws`).

2. **Messages sent while a client is disconnected are NOT backfilled on
   reconnect, by design.** `say`/room narration are transient broadcasts — they
   are not written to the audit feed (`recent_for_room`), so neither a page
   reload nor `reconnect_sync` can recover them; `reconnect_sync` re-syncs the
   room/inventory/players/time panels only. Replaying missed room chatter would
   require persisting it durably — a product/design decision (many MUDs
   deliberately don't), not a bug this test asserts. This test therefore proves
   reconnection restores **live** delivery, which is the reconnect feature's
   actual value; the backfill of transient chatter is out of scope.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.e2e._helpers import (
    create_character,
    drop_ws,
    send_command,
    wait_for_ws_connected,
    wait_for_ws_disconnected,
)

pytestmark = pytest.mark.e2e


def test_ws_reconnects_and_resumes_live_delivery(
    page: Any, second_page: Any, live_server: str
) -> None:
    """P5.1: after a forced socket drop, B auto-reconnects and again receives
    A's live room broadcasts."""
    username_a = f"e2e_a_{uuid.uuid4().hex[:8]}"
    username_b = f"e2e_b_{uuid.uuid4().hex[:8]}"

    create_character(page, live_server, username_a)
    create_character(second_page, live_server, username_b)
    wait_for_ws_connected(page)
    wait_for_ws_connected(second_page)

    # Sanity: live delivery works before the drop.
    send_command(page, "say before drop")
    second_page.locator("#feed", has_text="before drop").wait_for()

    # Force a genuine socket drop on B, then wait for app.js to reconnect.
    drop_ws(second_page)
    wait_for_ws_disconnected(second_page)
    wait_for_ws_connected(second_page)  # backoff reconnect (~1s); generous default

    # A sends a NEW message after B is back — B receives it live again.
    send_command(page, "say after reconnect")
    second_page.locator("#feed", has_text="after reconnect").wait_for()
