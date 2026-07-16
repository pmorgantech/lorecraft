"""Browser e2e: the admin Economy tab's per-zone region pricing table (Sprint 76.3).

The server-side contract (auth-gating, validation, persistence) is exercised by
the backend's own integration tests for `webui/admin/routers/economy.py`. This
file only exercises the client-side behaviour in `admin/index.html`: the table
loads the regions seeded from `world.yaml`'s `economy.regions:` list, editing +
saving a row's `region_mult` persists it live (no restart/reseed — a follow-up
load reflects the change), the save controls are gated to the superadmin role
the same way Progression's are (`tests/e2e/test_admin_progression_ui.py`), and
an invalid bias JSON value is caught client-side with an inline error instead
of being POSTed.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.conftest import admin_login

pytestmark = pytest.mark.e2e


def _open_economy_tab(page: Any) -> None:
    page.click('.category-tab[data-category="tuning"]')
    page.click('.tab[data-tab="economy"]')
    page.wait_for_selector("#economy-tbody", state="visible")
    # Wait for at least one seeded row to render before asserting on it.
    page.wait_for_function(
        "() => document.getElementById('economy-tbody').children.length > 0"
    )


def test_tab_loads_regions_seeded_from_world_yaml(page: Any, admin_server: str) -> None:
    admin_login(page, admin_server)
    _open_economy_tab(page)

    # world_content/world.yaml's `economy.regions:` list (see docs/roadmap.md
    # Sprint 71.2) seeds these four zones on world import, none with a bias.
    assert page.input_value("#eco-mult-ashmoore") == "1"
    assert page.input_value("#eco-mult-cogsworth") == "1.1"
    assert page.input_value("#eco-mult-whisperwood") == "1.05"
    assert page.input_value("#eco-mult-port_veridian") == "0.95"
    assert page.input_value("#eco-bias-cogsworth") == "{}"


def test_editing_region_mult_persists_and_reflects_on_reload(
    page: Any, admin_server: str
) -> None:
    admin_login(page, admin_server)
    _open_economy_tab(page)

    # This mutates the seeded `cogsworth` region -- restore it in `finally` so
    # the shared zone is left exactly as world.yaml seeded it regardless of
    # test order or a re-run of just this test (test_tab_loads_regions_seeded_
    # from_world_yaml asserts cogsworth's pristine 1.1/{} values). `admin_server`
    # already gives each test its own tmp_path DB today, but restoring here is
    # cheap defense against that isolation assumption changing later.
    try:
        page.fill("#eco-mult-cogsworth", "0.9")
        page.fill("#eco-bias-cogsworth", '{"gem": 2.0}')

        with page.expect_response("**/admin/economy/regions/cogsworth"):
            page.click("#eco-save-cogsworth")
        page.wait_for_function(
            "() => document.getElementById('eco-status-cogsworth').textContent.includes('Saved')"
        )

        # A follow-up load (simulating a fresh admin session, not a page reload of
        # stale form state) must reflect the change -- proving it's live in the
        # DB, not just held in the form -- no restart/reseed required.
        page.click('.category-tab[data-category="overview"]')
        page.click('.tab[data-tab="dashboard"]')
        _open_economy_tab(page)
        page.wait_for_function(
            "() => document.getElementById('eco-mult-cogsworth').value === '0.9'"
        )
        assert page.input_value("#eco-bias-cogsworth") == '{"gem":2}'

        # An untouched zone's row must be unaffected by the edit above.
        assert page.input_value("#eco-mult-whisperwood") == "1.05"
    finally:
        page.fill("#eco-mult-cogsworth", "1.1")
        page.fill("#eco-bias-cogsworth", "{}")
        with page.expect_response("**/admin/economy/regions/cogsworth"):
            page.click("#eco-save-cogsworth")
        page.wait_for_function(
            "() => document.getElementById('eco-status-cogsworth').textContent.includes('Saved')"
        )


def test_save_controls_gated_to_superadmin_role(page: Any, admin_server: str) -> None:
    admin_login(page, admin_server)
    _open_economy_tab(page)

    # The seeded e2e admin is a superadmin (see conftest.admin_server) -> enabled.
    assert page.is_enabled("#eco-save-cogsworth")
    assert page.is_enabled("#eco-mult-cogsworth")
    assert page.is_enabled("#eco-bias-cogsworth")

    # Simulate a lesser role the same way test_admin_progression_ui.py does --
    # there is no world-builder login fixture, so this is the lightest way to
    # exercise the client-side gate without adding a second seeded account.
    page.evaluate("() => { state.role = 'world-builder'; updateEconomyEditUI(); }")
    assert not page.is_enabled("#eco-save-cogsworth")
    assert not page.is_enabled("#eco-mult-cogsworth")
    assert not page.is_enabled("#eco-bias-cogsworth")
    title = (page.get_attribute("#eco-save-cogsworth", "title") or "").lower()
    assert "superadmin" in title

    page.evaluate("() => { state.role = 'superadmin'; updateEconomyEditUI(); }")
    assert page.is_enabled("#eco-save-cogsworth")
    assert page.is_enabled("#eco-mult-cogsworth")


def test_invalid_bias_json_shows_inline_error_without_posting(
    page: Any, admin_server: str
) -> None:
    admin_login(page, admin_server)
    _open_economy_tab(page)

    posted_zones: list[str] = []
    page.on(
        "request",
        lambda req: (
            posted_zones.append(req.url)
            if req.method == "POST" and "/admin/economy/regions/" in req.url
            else None
        ),
    )

    page.fill("#eco-bias-cogsworth", "{not valid json")
    page.click("#eco-save-cogsworth")
    page.wait_for_function(
        "() => document.getElementById('eco-status-cogsworth').textContent.length > 0"
    )
    assert "invalid" in page.text_content("#eco-status-cogsworth").lower()
    assert posted_zones == []

    # A structurally-valid-JSON-but-wrong-shape value (non-numeric mult) is
    # also rejected client-side before it ever reaches the network.
    page.fill("#eco-bias-cogsworth", '{"gem": "two"}')
    page.click("#eco-save-cogsworth")
    page.wait_for_function(
        "() => document.getElementById('eco-status-cogsworth').textContent.length > 0"
    )
    assert "number" in page.text_content("#eco-status-cogsworth").lower()
    assert posted_zones == []
