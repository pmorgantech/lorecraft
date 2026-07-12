"""Browser e2e: the admin Progression tab's XP-curve/reward config form (Sprint 73.4).

The server-side contract (auth-gating, validation, persistence) is exercised by
the backend's own integration tests. This file only exercises the client-side
behaviour in `admin/index.html`: the form loads the config seeded from
`world.yaml`, editing + saving persists it live (no restart/reseed — a
follow-up load reflects the change), and the save control is gated to the
superadmin role the same way the World reseed button is
(`tests/e2e/test_admin_world_reseed_ui.py`).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.conftest import admin_login

pytestmark = pytest.mark.e2e


def _open_progression_tab(page: Any) -> None:
    page.click('.tab[data-tab="progression"]')
    page.wait_for_selector("#pg-save-btn", state="visible")


def test_form_loads_config_seeded_from_world_yaml(page: Any, admin_server: str) -> None:
    admin_login(page, admin_server)
    _open_progression_tab(page)

    # world_content/world.yaml's `progression:` section (see docs/roadmap.md
    # Sprint 73.3) seeds these on world import.
    page.wait_for_function("() => document.getElementById('pg-base').value !== ''")
    assert page.input_value("#pg-base") == "100"
    assert page.input_value("#pg-step") == "50"
    assert page.input_value("#pg-coins") == "25"
    assert page.input_value("#pg-skill-points") == "1"


def test_editing_and_saving_persists_and_reflects_on_reload(
    page: Any, admin_server: str
) -> None:
    admin_login(page, admin_server)
    _open_progression_tab(page)
    page.wait_for_function("() => document.getElementById('pg-base').value !== ''")

    page.fill("#pg-base", "150")
    page.fill("#pg-step", "60")
    page.fill("#pg-coins", "40")
    page.fill("#pg-skill-points", "2")

    with page.expect_response("**/admin/progression/config"):
        page.click("#pg-save-btn")
    page.wait_for_function(
        "() => document.getElementById('pg-save-status').textContent.includes('Saved')"
    )

    # A follow-up load (simulating a fresh admin session, not a page reload
    # of stale form state) must reflect the change -- proving it's live in
    # the DB, not just held in the form -- no restart/reseed required.
    page.click('.tab[data-tab="dashboard"]')
    _open_progression_tab(page)
    page.wait_for_function("() => document.getElementById('pg-base').value === '150'")
    assert page.input_value("#pg-step") == "60"
    assert page.input_value("#pg-coins") == "40"
    assert page.input_value("#pg-skill-points") == "2"


def test_save_control_gated_to_superadmin_role(page: Any, admin_server: str) -> None:
    admin_login(page, admin_server)
    _open_progression_tab(page)
    page.wait_for_function("() => document.getElementById('pg-base').value !== ''")

    # The seeded e2e admin is a superadmin (see conftest.admin_server) -> enabled.
    assert page.is_enabled("#pg-save-btn")
    assert page.is_enabled("#pg-base")

    # Simulate a lesser role the same way test_admin_world_reseed_ui.py does --
    # there is no world-builder login fixture, so this is the lightest way to
    # exercise the client-side gate without adding a second seeded account.
    page.evaluate("() => { state.role = 'world-builder'; updateProgressionEditUI(); }")
    assert not page.is_enabled("#pg-save-btn")
    assert not page.is_enabled("#pg-base")
    title = (page.get_attribute("#pg-save-btn", "title") or "").lower()
    assert "superadmin" in title

    page.evaluate("() => { state.role = 'superadmin'; updateProgressionEditUI(); }")
    assert page.is_enabled("#pg-save-btn")
    assert page.is_enabled("#pg-base")
