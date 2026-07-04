"""
Test that the WebUI properly refreshes when items are taken/dropped.

Regression test for two related bugs found 2026-07-04:
1. Room items list ("You notice:") not refreshing after 'get all'
   — the CURRENT LOCATION pane showed stale items while inventory was correct
2. Actor seeing both their own action message AND the room narration
   — "You take X" and "player_name takes X" both appeared to the actor
"""

import pytest


@pytest.mark.e2e
async def test_get_all_refreshes_room_items_pane(live_server, browser, ashmoore_player):
    """Verify that 'get all' removes items from room display."""
    page = browser
    await page.goto(f"{live_server}/lobby")

    # Log in as the player
    await page.fill('input[name="username"]', ashmoore_player.username)
    await page.click('button:has-text("Continue")')
    await page.wait_for_url(f"{live_server}/game")

    # Navigate to Locksmith's Gallery (has multiple items)
    await page.fill('input[name="command"]', "south")
    await page.press('input[name="command"]', "Enter")
    await page.wait_for_selector("text=Locksmith's Gallery", timeout=2000)

    # Verify items are visible in the room pane ("You notice:")
    room_pane = await page.query_selector("#room-description")
    text_before = await room_pane.text_content()
    assert "You notice:" in text_before
    assert "Key" in text_before, "Expected keys in Locksmith's Gallery"

    # Get all items
    await page.fill('input[name="command"]', "get all")
    await page.press('input[name="command"]', "Enter")

    # The feed should show success
    feed = await page.query_selector("#feed")
    feed_text = await feed.text_content()
    assert "You take" in feed_text

    # CRITICAL: The room pane should now be EMPTY (no "You notice:" or items listed)
    await page.wait_for_function(
        """() => {
            const roomPane = document.querySelector('#room-description');
            if (!roomPane) return false;
            const text = roomPane.textContent;
            // Should not have "You notice: Key" anymore
            return !text.includes('You notice: ') || !text.includes('Key');
        }""",
        timeout=2000,
    )
    room_pane_after = await page.query_selector("#room-description")
    text_after = await room_pane_after.text_content()
    assert "You notice:" not in text_after or "Key" not in text_after, (
        f"Room pane not updated after 'get all'. Still shows: {text_after}"
    )

    # Inventory should have the items
    inv_pane = await page.query_selector("#inventory")
    inv_text = await inv_pane.text_content()
    assert "Key" in inv_text


@pytest.mark.e2e
async def test_actor_only_sees_own_message_not_room_narration(
    live_server, browser, ashmoore_player
):
    """Verify that the actor doesn't see the room narration of their own action."""
    page = browser
    await page.goto(f"{live_server}/lobby")

    # Log in
    await page.fill('input[name="username"]', ashmoore_player.username)
    await page.click('button:has-text("Continue")')
    await page.wait_for_url(f"{live_server}/game")

    # Navigate to a room with items
    await page.fill('input[name="command"]', "south")
    await page.press('input[name="command"]', "Enter")
    await page.wait_for_selector("text=Locksmith's Gallery", timeout=2000)

    # Do an action that produces room narration
    await page.fill('input[name="command"]', "get cage key")
    await page.press('input[name="command"]', "Enter")

    # Get the feed text
    feed = await page.query_selector("#feed")
    await page.wait_for_function(
        """() => {
            const feed = document.querySelector('#feed');
            return feed && feed.textContent.includes('take');
        }""",
        timeout=2000,
    )
    feed_text = await feed.text_content()

    # The feed should show "You take Cage Key" (actor message)
    assert "You take" in feed_text

    # CRITICAL: The feed should NOT also show "ashmoore_player takes Cage Key" (room narration)
    # The room narration is broadcast to OTHER players, not the actor
    lines = feed_text.split("\n")
    take_lines = [
        line for line in lines if "take" in line.lower() and "Cage Key" in line
    ]

    # Should be exactly 1 message about taking the cage key (the actor version)
    # NOT 2 (which would mean actor is seeing both their message AND the room narration)
    assert len(take_lines) == 1, (
        f"Actor should see only 'You take' message, not room narration. Got: {take_lines}"
    )
    assert "You take" in take_lines[0], "Actor should see their own 'You take' message"
