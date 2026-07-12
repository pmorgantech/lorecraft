"""Browser e2e: every admin console tab stays reachable regardless of window width.

`#tab-bar` grows by one entry almost every sprint. Its container (`#admin-body`)
clips overflow, so without an explicit horizontal-scroll affordance on the tab
bar itself, the newest tab(s) silently fall off the edge on a narrower window —
found live: the System tab (added last, Sprint 72) was invisible on a phone in
landscape, with no scrollbar or any visual cue that more tabs existed. This
pins the fix (`overflow-x: auto` + `flex-shrink: 0` on `.tab`) rather than
relying on window width being "wide enough."
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.conftest import admin_login

pytestmark = pytest.mark.e2e


def test_last_tab_reachable_via_scroll_on_a_narrow_viewport(
    page: Any, admin_server: str
) -> None:
    # Narrower than every tab's combined width, matching the phone report.
    page.set_viewport_size({"width": 900, "height": 500})
    admin_login(page, admin_server)

    tab_bar = page.locator("#tab-bar")
    system_tab = page.locator('.tab[data-tab="system"]')

    # The bar must actually overflow at this width -- otherwise this test would
    # pass trivially without exercising the scroll fix at all.
    scroll_width = tab_bar.evaluate("el => el.scrollWidth")
    client_width = tab_bar.evaluate("el => el.clientWidth")
    assert scroll_width > client_width, (
        "tab bar doesn't overflow at this viewport width; widen the test's "
        "viewport or add more tabs so this test still exercises the scroll fix"
    )

    # Before scrolling, the last tab is out of view (this is the reported bug's
    # starting state -- not itself the assertion, just documenting it).
    tab_bar.evaluate("el => { el.scrollLeft = 0; }")

    # Scrolling the bar all the way right must bring System fully into view.
    tab_bar.evaluate("el => { el.scrollLeft = el.scrollWidth; }")
    box = system_tab.bounding_box()
    assert box is not None
    assert box["x"] >= 0
    assert box["x"] + box["width"] <= 900

    # And it must actually be clickable/functional once scrolled into view --
    # not just visually present.
    system_tab.click()
    page.wait_for_selector("#tab-system", state="visible")
    assert "active" in (system_tab.get_attribute("class") or "")
