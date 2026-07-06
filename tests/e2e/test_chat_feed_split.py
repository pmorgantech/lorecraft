"""Chat/feed split e2e (Sprint 45.2, `docs/chat_feed_split.md` Phase 2).

Two real browser contexts against one live server: a speaker with the default
single feed, and a listener who turned the `separate_chat` preference on via
the settings page. Verifies the plan's acceptance scenario end to end:

- speaker's `say` reaches the listener's **chat pane**, not their narrative
  feed (WS `feed_append`/`message_type:"chat"` routing);
- the listener's own `say` echo lands in their chat pane too (HTMX response
  routing via `routeChatMessages`);
- movement narration ("X leaves east.") stays in the **narrative feed** for
  everyone;
- with the preference off (the speaker), there is no chat pane and chat
  renders in the single feed exactly as before.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.conftest import create_character

pytestmark = pytest.mark.e2e


def _send_command(page: Any, command: str) -> None:
    page.fill("#command-input", command)
    page.press("#command-input", "Enter")
    page.wait_for_function("document.getElementById('command-input').value === ''")


def _enable_separate_chat(page: Any, base_url: str) -> None:
    page.goto(f"{base_url}/settings")
    page.check("input[name='separate_chat']")
    page.click("button[type='submit']")
    page.wait_for_selector("input[name='separate_chat']:checked")
    page.goto(f"{base_url}/game")
    page.wait_for_selector("#chat-pane")


def test_say_routes_to_chat_pane_only_for_opted_in_players(
    browser: Any, live_server: str
) -> None:
    speaker_context = browser.new_context()
    listener_context = browser.new_context()
    try:
        speaker = speaker_context.new_page()
        listener = listener_context.new_page()

        create_character(speaker, live_server, "e2e_speaker")
        create_character(listener, live_server, "e2e_listener")

        # Listener opts in; speaker keeps the default single feed (no pane).
        _enable_separate_chat(listener, live_server)
        assert speaker.locator("#chat-pane").count() == 0

        # Give both WS connections a beat to attach before broadcasting.
        speaker.wait_for_timeout(300)
        listener.wait_for_timeout(300)

        # NB: keep the phrase preposition-free — the parser treats "from/with/
        # to …" as command roles and would truncate the say noun.
        _send_command(speaker, "say hello everyone")

        # Listener (pref on): chat lands in the chat pane, not the feed.
        listener.wait_for_selector(
            "#chat-feed :text('e2e_speaker says: \"hello everyone\"')"
        )
        assert listener.locator("#feed :text('hello everyone')").count() == 0

        # Speaker (pref off): own echo renders in the single feed.
        speaker.wait_for_selector("#feed :text('You say: \"hello everyone\"')")

        # Listener's own say echo routes to their chat pane (HTMX path).
        _send_command(listener, "say hi back")
        listener.wait_for_selector("#chat-feed :text('You say: \"hi back\"')")
        assert listener.locator("#feed :text('You say: \"hi back\"')").count() == 0

        # Movement narration stays in the narrative feed for the listener.
        _send_command(speaker, "go east")
        listener.wait_for_selector("#feed :text('e2e_speaker')")
        assert listener.locator("#chat-feed :text('leaves')").count() == 0
    finally:
        speaker_context.close()
        listener_context.close()
