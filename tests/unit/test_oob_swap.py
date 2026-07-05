"""Unit tests for HTMX OOB swap markup helper."""

from __future__ import annotations

from lorecraft.webui.player.rendering import mark_oob_swap


def test_mark_oob_swap_handles_multiline_opening_tag() -> None:
    html = '<div\n    id="dialogue-overlay"\n    class="dialogue-overlay flex">\n</div>'
    marked = mark_oob_swap(html, "dialogue-overlay")
    assert 'id="dialogue-overlay" hx-swap-oob="true"' in marked


def test_mark_oob_swap_is_noop_when_id_missing() -> None:
    html = '<div class="other">x</div>'
    assert mark_oob_swap(html, "dialogue-overlay") == html
