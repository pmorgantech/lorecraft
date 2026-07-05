"""Registered issue components — the closed set an issue may relate to.

Coarse, structural areas of the codebase (not per-feature), so triage stays
simple and filterable. This is the single source of truth: the admin API serves
it to the console dropdown (`GET /admin/issues/components`) and validates writes
against it. An empty component ("") is always allowed — it means "unassigned",
which is the default for in-game player reports.
"""

from __future__ import annotations

ISSUE_COMPONENTS: tuple[str, ...] = (
    "engine",
    "webui/player",
    "webui/admin",
    "admin-tui",
    "features",
    "docs",
    "infra",
)


def is_valid_component(value: str) -> bool:
    """True if `value` is a registered component or the empty (unassigned) value."""
    return value == "" or value in ISSUE_COMPONENTS
