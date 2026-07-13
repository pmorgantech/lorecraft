"""Browser e2e tests for the `help` command's rendered output.

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

from tests.e2e._helpers import create_character, send_command

pytestmark = pytest.mark.e2e


def test_help_output_preserves_line_breaks(page: Any, live_server: str) -> None:
    """Regression test (2026-07-04): `help`'s multi-line output (joined with
    "\\n") rendered as one giant wrapped paragraph, because the feed message
    span had no whitespace styling and browsers collapse literal newlines by
    default. The message span must preserve them (whitespace-pre-line)."""
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    # `help commands` is the multi-line grouped list (bare `help` is now a short
    # curated set); either way the span must preserve newlines.
    send_command(page, "help commands")

    message_span = page.locator("#feed .msg", has_text="All commands").locator(
        "span.whitespace-pre-line"
    )
    message_span.wait_for()
    white_space = message_span.evaluate("el => getComputedStyle(el).whiteSpace")
    assert white_space == "pre-line"


def test_help_output_gets_bold_accent_styling(page: Any, live_server: str) -> None:
    """Sprint 71.4: `help`'s documentation output is tagged
    `MessageType.HELP` (`msg_type: "help"`), which the feed templates turn
    into an additive `msg-help` class on the `.msg` div (Sprint 56 hook).
    Confirms the CSS actually renders it distinctly (bold) — not just that
    the class string is present — since a same-file base rule for `.msg`
    (`#feed .msg, .msg { border-left: 2px solid transparent; }`) carries an
    ID selector that would otherwise beat a plain `.msg.msg-help` class rule
    on specificity and silently no-op it."""
    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, live_server, username)

    send_command(page, "help commands")

    message = page.locator("#feed .msg.msg-help", has_text="All commands")
    message.wait_for()
    font_weight = message.evaluate("el => getComputedStyle(el).fontWeight")
    # Browsers normalize named weights ("bold") to numeric ("700"); either
    # form clears "normal"/400.
    assert font_weight not in ("normal", "400")
