"""Browser e2e: admin Issues tab inline editing (priority, description).

Split from test_admin_issues.py (2026-07-13) for xdist file-level
parallelism. Seeds issues via the REST API, then drives the real admin
console in a headless browser to verify inline edits round-trip to the
backend.
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


def _open_issues_tab(page: Any, base_url: str) -> None:
    admin_login(page, base_url)
    page.click('.category-tab[data-category="moderation"]')
    page.click('.tab[data-tab="issues"]')


def test_edit_priority_via_row_select(page: Any, admin_server: str) -> None:
    token = _token(admin_server)
    issue_id = _seed_issue(admin_server, token, "Reprioritize me", priority="low")

    _open_issues_tab(page, admin_server)
    page.wait_for_selector(f"#issue-caret-{issue_id}")

    row = page.locator(f"tr:has(#issue-caret-{issue_id})")
    priority_select = row.locator("select").nth(1)
    assert priority_select.input_value() == "low"
    priority_select.select_option("critical")

    # The change PUTs to the backend and reloads the list; wait for the
    # re-rendered row to reflect the new priority before asserting server state.
    page.wait_for_selector(
        f"tr:has(#issue-caret-{issue_id}) option[value='critical'][selected]",
        state="attached",
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(f"{admin_server}/admin/issues/{issue_id}", headers=headers)
    assert resp.json()["priority"] == "critical"


def test_edit_description_via_detail_textarea(page: Any, admin_server: str) -> None:
    token = _token(admin_server)
    issue_id = _seed_issue(admin_server, token, "Needs a description")

    _open_issues_tab(page, admin_server)
    page.wait_for_selector(f"#issue-caret-{issue_id}")

    # Open the detail row (click anywhere on the summary row outside a select).
    page.click(f"#issue-caret-{issue_id}")
    textarea = page.locator(f"#issue-desc-{issue_id}")
    textarea.fill("Steps to reproduce: do the thing.")
    page.click(f"tr#issue-detail-{issue_id} button:has-text('Save')")

    # Save PUTs + reloads; wait for the fresh detail row's textarea to carry
    # the server-confirmed value back before asserting on the API directly.
    page.wait_for_function(
        "(id) => { const ta = document.getElementById(`issue-desc-${id}`);"
        " return ta && ta.value === 'Steps to reproduce: do the thing.'; }",
        arg=issue_id,
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(f"{admin_server}/admin/issues/{issue_id}", headers=headers)
    assert resp.json()["description"] == "Steps to reproduce: do the thing."
