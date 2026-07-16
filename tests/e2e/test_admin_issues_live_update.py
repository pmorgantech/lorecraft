"""Browser e2e: admin Issues tab live-refresh on out-of-band creation.

Split from test_admin_issues.py (2026-07-13) for xdist file-level
parallelism. Seeds issues via the REST API, then drives the real admin
console in a headless browser to verify an issue created out-of-band (another
admin, or a player report) appears without a manual reload.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.e2e.conftest import ADMIN_PASS, ADMIN_USER, admin_login

pytestmark = pytest.mark.e2e


def _token(base_url: str) -> str:
    resp = httpx.post(
        f"{base_url}/admin/auth/token",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    return resp.json()["access_token"]


def _seed_issue(
    base_url: str,
    token: str,
    title: str,
    *,
    priority: str = "normal",
    status: str = "open",
) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    created = httpx.post(
        f"{base_url}/admin/issues",
        json={"title": title, "priority": priority},
        headers=headers,
    ).json()
    if status != "open":
        httpx.put(
            f"{base_url}/admin/issues/{created['id']}",
            json={"status": status},
            headers=headers,
        )
    return created["id"]


def _displayed_ids(page: Any) -> list[str]:
    """Issue ids in on-screen order (summary rows carry an issue-caret-<id>)."""
    return page.evaluate(
        "() => Array.from(document.querySelectorAll(\"#issues-tbody [id^='issue-caret-']\"))"
        ".map(e => e.id.replace('issue-caret-', ''))"
    )


def _open_issues_tab(page: Any, base_url: str) -> None:
    admin_login(page, base_url)
    page.click('.category-tab[data-category="moderation"]')
    page.click('.tab[data-tab="issues"]')


def test_issue_tab_live_updates_on_out_of_band_create(
    page: Any, admin_server: str
) -> None:
    _open_issues_tab(page, admin_server)
    page.wait_for_selector("#issues-tbody")

    # A create the open tab did not initiate (another admin, or a player report
    # via the ISSUE_FILED broadcast) must appear without a manual reload.
    token = _token(admin_server)
    new_id = _seed_issue(admin_server, token, "Live update marker", priority="high")

    page.wait_for_selector(f"#issue-caret-{new_id}", timeout=5000)
    assert new_id in _displayed_ids(page)
