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

from tests.e2e._helpers import (
    create_character,
    enable_separate_chat,
    send_command_via_enter,
)

pytestmark = pytest.mark.e2e


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
        enable_separate_chat(listener, live_server)
        assert speaker.locator("#chat-pane").count() == 0

        # Give both WS connections a beat to attach before broadcasting.
        speaker.wait_for_timeout(300)
        listener.wait_for_timeout(300)

        # NB: keep the phrase preposition-free — the parser treats "from/with/
        # to …" as command roles and would truncate the say noun.
        send_command_via_enter(speaker, "say hello everyone")

        # Listener (pref on): chat lands in the chat pane, not the feed.
        listener.wait_for_selector(
            "#chat-feed :text('e2e_speaker says: \"hello everyone\"')"
        )
        assert listener.locator("#feed :text('hello everyone')").count() == 0

        # Speaker (pref off): own echo renders in the single feed.
        speaker.wait_for_selector("#feed :text('You say: \"hello everyone\"')")

        # Listener's own say echo routes to their chat pane (HTMX path).
        send_command_via_enter(listener, "say hi back")
        listener.wait_for_selector("#chat-feed :text('You say: \"hi back\"')")
        assert listener.locator("#feed :text('You say: \"hi back\"')").count() == 0

        # Movement narration stays in the narrative feed for the listener.
        send_command_via_enter(speaker, "go east")
        listener.wait_for_selector("#feed :text('e2e_speaker')")
        assert listener.locator("#chat-feed :text('leaves')").count() == 0
    finally:
        speaker_context.close()
        listener_context.close()


def _unsubscribe_newbie(page: Any, base_url: str) -> None:
    """Untick the Newbie channel subscription on the settings page (Sprint
    52.8's per-channel toggle list) and return to /game."""
    page.goto(f"{base_url}/settings")
    page.uncheck("input[name='channel_sub_newbie']")
    page.click("button[type='submit']")
    page.wait_for_selector("input[name='channel_sub_newbie']:not(:checked)")
    page.goto(f"{base_url}/game")
    page.wait_for_selector("#command-input")


def test_newbie_channel_reaches_subscribers_and_skips_the_muted(
    browser: Any, live_server: str
) -> None:
    """Sprint 52: a P2ALL topic message reaches a subscribed player anywhere
    in the world, styled with its channel class — and is dropped server-side
    for a player who unsubscribed via the settings channel list."""
    speaker_context = browser.new_context()
    subscribed_context = browser.new_context()
    muted_context = browser.new_context()
    try:
        speaker = speaker_context.new_page()
        subscribed = subscribed_context.new_page()
        muted = muted_context.new_page()

        create_character(speaker, live_server, "e2e_talker")
        create_character(subscribed, live_server, "e2e_hearer")
        create_character(muted, live_server, "e2e_muted")

        # The subscribed listener uses the chat pane so the per-channel class
        # path is exercised; subscription itself is the default (on).
        enable_separate_chat(subscribed, live_server)
        _unsubscribe_newbie(muted, live_server)

        # Put the subscribed listener in another room — P2ALL must still reach
        # them (unlike room-scoped say).
        send_command_via_enter(subscribed, "go east")

        speaker.wait_for_timeout(300)
        subscribed.wait_for_timeout(300)
        muted.wait_for_timeout(300)

        send_command_via_enter(speaker, "newbie anybody around")

        # Speaker's own echo, prefixed.
        speaker.wait_for_selector("#feed :text('(Newbie) You: \"anybody around\"')")

        # Subscribed listener in another room: tagged, in the chat pane, with
        # the per-channel class (Sprint 52.7).
        subscribed.wait_for_selector(
            "#chat-feed :text('(Newbie) e2e_talker: \"anybody around\"')"
        )
        assert subscribed.locator("#chat-feed .msg.chat-newbie").count() >= 1

        # Muted listener: the server never sent it.
        muted.wait_for_timeout(600)
        assert muted.locator(":text('anybody around')").count() == 0
    finally:
        speaker_context.close()
        subscribed_context.close()
        muted_context.close()


def test_tell_reaches_only_its_target(browser: Any, live_server: str) -> None:
    """Sprint 52: `tell` is P2P — the target sees it (tagged tell), a
    bystander in the same room never does, and the sender gets an echo."""
    sender_context = browser.new_context()
    target_context = browser.new_context()
    bystander_context = browser.new_context()
    try:
        sender = sender_context.new_page()
        target = target_context.new_page()
        bystander = bystander_context.new_page()

        create_character(sender, live_server, "e2e_sender")
        create_character(target, live_server, "e2e_target")
        create_character(bystander, live_server, "e2e_bystander")

        sender.wait_for_timeout(300)
        target.wait_for_timeout(300)
        bystander.wait_for_timeout(300)

        send_command_via_enter(sender, "tell e2e_target meet me later")

        sender.wait_for_selector(
            "#feed :text('You tell e2e_target: \"meet me later\"')"
        )
        target.wait_for_selector(
            "#feed :text('e2e_sender tells you: \"meet me later\"')"
        )
        bystander.wait_for_timeout(600)
        assert bystander.locator(":text('meet me later')").count() == 0

        # Offline rejection: nobody by that name is connected.
        send_command_via_enter(sender, "tell e2e_nobody hello")
        sender.wait_for_selector('#feed :text("There\'s no one called")')
    finally:
        sender_context.close()
        target_context.close()
        bystander_context.close()
