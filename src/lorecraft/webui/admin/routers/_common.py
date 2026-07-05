"""Shared helpers for admin content routers."""

from __future__ import annotations

from typing import Any


def notify_content_changed(state: Any, resource: str) -> None:
    """Push a live-refresh hint to all connected admin consoles.

    Content routers (issues/news/help) call this after a mutation so open admin
    sessions can reload the affected tab without a manual refresh. `resource`
    matches a frontend tab id (e.g. "issues", "news", "help"). Best-effort: the
    broadcaster silently drops the message for any full/slow queue.
    """
    state.admin_broadcaster.push({"type": "content_changed", "resource": resource})
