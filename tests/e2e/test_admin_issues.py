"""Browser e2e: admin Issues tab filtering, sorting, and live updates.

Seeds issues via the REST API, then drives the real admin console in a headless
browser to verify the client-side default filter (hide resolved/deferred),
selectable sort, and live-refresh when an issue is created out-of-band.
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
    page.click('.tab[data-tab="issues"]')


def test_default_hides_resolved_and_deferred(page: Any, admin_server: str) -> None:
    token = _token(admin_server)
    open_id = _seed_issue(admin_server, token, "Open one", status="open")
    prog_id = _seed_issue(admin_server, token, "In progress", status="in-progress")
    res_id = _seed_issue(admin_server, token, "Resolved one", status="resolved")
    def_id = _seed_issue(admin_server, token, "Deferred one", status="deferred")

    _open_issues_tab(page, admin_server)
    page.wait_for_selector(f"#issue-caret-{open_id}")

    ids = _displayed_ids(page)
    assert open_id in ids and prog_id in ids
    assert res_id not in ids and def_id not in ids  # hidden by default

    # Unchecking "resolved" in the Hide group brings resolved issues back.
    page.uncheck("#i-hide-group input[value='resolved']")
    page.wait_for_selector(f"#issue-caret-{res_id}")
    ids = _displayed_ids(page)
    assert res_id in ids
    assert def_id not in ids  # still hidden


def test_sort_by_priority(page: Any, admin_server: str) -> None:
    token = _token(admin_server)
    low = _seed_issue(admin_server, token, "low one", priority="low")
    crit = _seed_issue(admin_server, token, "crit one", priority="critical")
    norm = _seed_issue(admin_server, token, "norm one", priority="normal")
    high = _seed_issue(admin_server, token, "high one", priority="high")

    _open_issues_tab(page, admin_server)
    page.wait_for_selector(f"#issue-caret-{crit}")

    # Default sort is priority: critical, high, normal, low.
    assert _displayed_ids(page) == [crit, high, norm, low]


def test_sort_by_recently_created(page: Any, admin_server: str) -> None:
    token = _token(admin_server)
    # Same priority so the date key (not the priority tiebreak) decides order.
    first = _seed_issue(admin_server, token, "first", priority="normal")
    second = _seed_issue(admin_server, token, "second", priority="normal")
    third = _seed_issue(admin_server, token, "third", priority="normal")

    _open_issues_tab(page, admin_server)
    page.wait_for_selector(f"#issue-caret-{first}")

    page.select_option("#i-sort", "created")
    # Wait for the re-render to put the newest-created first.
    page.wait_for_function(
        "(id) => { const e = document.querySelectorAll(\"#issues-tbody [id^='issue-caret-']\");"
        " return e.length && e[0].id === 'issue-caret-' + id; }",
        arg=third,
    )
    assert _displayed_ids(page) == [third, second, first]


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
