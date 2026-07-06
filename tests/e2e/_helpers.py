"""Shared helpers for e2e browser tests.

These utilities reduce duplication across test files and ensure consistent
patterns for common operations (character creation, command submission, etc.).

## Multiplayer Testing Pattern (WS Async Broadcast)

When testing cross-client updates (one player acts, another observes a broadcast),
remember that **WebSocket broadcasts are asynchronous**: after Player A acts,
Player B's DOM updates on the next event loop turn, not synchronously in the same
stack frame.

**Rule: never bare-assert immediately after a cross-client action.**

Always use `page.wait_for_function()` or `locator.wait_for()` on the receiver's DOM:

    # ✅ CORRECT: wait for B's state to change via the broadcast
    a_send_command(page_a, "say hello")
    page_b.wait_for_selector("#feed :text('hello')")

    # ❌ WRONG: immediate assert, B's update hasn't arrived yet
    a_send_command(page_a, "say hello")
    assert "hello" in page_b.locator("#feed").inner_text()  # flaky!

Before testing multiplayer behavior, ensure both connections are ready:

    create_character(page_a, live_server, "player_a")
    create_character(page_b, live_server, "player_b")
    wait_for_both_ws_connected(page_a, page_b)
    # Now safe to test cross-client updates
"""

from __future__ import annotations

import re
from typing import Any

# Default character password for e2e flows. Satisfies the lobby password policy
# (>=8 chars, mixed case, a digit — see config.py). Shared by create + login
# helpers so a login test can re-authenticate a just-created character.
CHARACTER_PASSWORD = "E2eTestPass1"


def create_character(page: Any, base_url: str, username: str) -> None:
    """Drive the lobby's new-character form through to /game.

    The create form gates its submit button on `formOk` = valid username +
    policy-compliant password + matching confirmation, so fill both password
    inputs with a compliant value (see the lobby template).
    """
    page.goto(f"{base_url}/lobby")
    page.click("text=Create New Character")
    page.fill("#username", username)
    page.fill("#create-password", CHARACTER_PASSWORD)
    page.fill("#create-password-confirm", CHARACTER_PASSWORD)
    page.click("text=Create & Enter")
    page.wait_for_url(re.compile(r".*/game$"))


def login_character(
    page: Any, base_url: str, username: str, password: str = CHARACTER_PASSWORD
) -> None:
    """Drive the lobby's *Log In* tab (the default tab) through to /game.

    Unlike create_character, this uses the existing-character login path
    (`POST /lobby/enter`, `allow_create=False`). Selectors are the Log In tab's
    `#enter-username` / `#enter-password` (create uses `#username` /
    `#create-password`). Only call this for a character that already exists with
    the given password; a bad/unknown login re-renders the lobby (see
    `expect_login_rejected`) rather than reaching /game.
    """
    page.goto(f"{base_url}/lobby")
    page.fill("#enter-username", username)
    page.fill("#enter-password", password)
    page.click("form[action='/lobby/enter'] button[type=submit]")
    page.wait_for_url(re.compile(r".*/game$"))


def send_command(page: Any, command: str) -> None:
    """Submit a command and wait for the HTMX round-trip to finish.

    handleCommandSuccess() clears #command-input only after the /command
    response has been swapped in, so polling for an empty value is a
    reliable, app-specific "request settled" signal.

    Supports both button click and Enter keypress submission paths.
    """
    page.fill("#command-input", command)
    page.click("#command-form button[type=submit]")
    page.wait_for_function("document.getElementById('command-input').value === ''")


def send_command_via_enter(page: Any, command: str) -> None:
    """Submit a command via Enter key (history-recording path).

    The history mechanism (setupCommandHistory in app.js) only records on the
    input's own "Enter" keydown, not on button click. Use this variant when
    testing command history features.
    """
    page.fill("#command-input", command)
    page.press("#command-input", "Enter")
    page.wait_for_function("document.getElementById('command-input').value === ''")


def enable_separate_chat(page: Any, base_url: str) -> None:
    """Navigate to settings, enable the separate_chat preference, and return to /game.

    After enabling, the #chat-pane element is present (or becomes visible)
    for further assertions in the test.
    """
    page.goto(f"{base_url}/settings")
    page.check("input[name='separate_chat']")
    page.click("button[type='submit']")
    page.wait_for_selector("input[name='separate_chat']:checked")
    page.goto(f"{base_url}/game")
    page.wait_for_selector("#chat-pane")


def navigate_to_locksmiths_gallery(page: Any) -> None:
    """Navigate from village_square to the key_gallery via the forge.

    Path: village_square --north--> blacksmith_forge --north--> key_gallery.
    Used by item-action tests.
    """
    send_command(page, "north")
    page.locator("#room-description", has_text="Forge and Hammer").wait_for()
    send_command(page, "north")
    page.locator("#room-description", has_text="Locksmith's Gallery").wait_for()


def wait_for_ws_connected(page: Any) -> None:
    """Wait for the WebSocket connection to become ready.

    The WS connection is established asynchronously on /game load: app.js
    fetches a single-use ticket (POST /auth/ws-ticket) and opens /ws. On
    ws.onopen it sets an internal flag exposed as `window.Lorecraft.isConnected()`.

    We can't use the header status dot (`.w-2.h-2.rounded-full`) as the signal
    because it is server-rendered already carrying `bg-emerald-500`, so it can't
    distinguish "connecting" from "connected".

    This signal is essential for multiplayer tests: the receiving player must be
    connected *before* the acting player triggers a room broadcast, or the push
    is sent to nobody. Broadcasts are only delivered to currently-open sockets.

    Usage: after create_character(), call this before another player acts.
    """
    page.wait_for_function(
        "window.Lorecraft && window.Lorecraft.isConnected && "
        "window.Lorecraft.isConnected() === true"
    )


def wait_for_both_ws_connected(page_a: Any, page_b: Any) -> None:
    """Wait for both pages to have WebSocket connections ready.

    Convenience helper for two-player tests: both contexts must be connected
    before one player acts and the other observes the broadcast.
    """
    wait_for_ws_connected(page_a)
    wait_for_ws_connected(page_b)


def set_offline(page: Any, offline: bool) -> None:
    """Set a page's context to offline/online mode.

    When offline=True, the browser disconnects from the network (simulating
    network failure). When offline=False, it reconnects. The `app.js`
    reconnect handler uses `app.js`'s reconnect + `reconnect_sync` backfill
    to restore state and catch up on missed messages.

    Used only in P5.1 (reconnect/resync test); kept separate because it is
    timing-sensitive and flaky. Wait for the "Session restored." system
    message after setting offline=False to confirm the backfill completed.
    """
    page.context.set_offline(offline)
