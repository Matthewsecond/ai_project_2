"""
Smoke test — log in, visit every tab, assert nothing threw.

This is the safety net for the ES-module split: if a module fails to load or calls a function
that wasn't imported, exercising its tab raises an uncaught exception, which `pageerror` records.

Nav model in index.html (post two-tab collapse): just the two top tabs, Search and Saved —
the old Candidate/Analytics mode toggle and the radar/map/analytics tabs were removed.

Run just this suite:  pytest tests/jobs_intelligence_ai/frontend/e2e -m e2e
"""
import pytest

pytestmark = pytest.mark.e2e

EXPECTED = ["search", "saved"]


def test_tabs_smoke(logged_in_page):
    page = logged_in_page

    exercised = []
    for tab in EXPECTED:
        btn = page.query_selector(f'.tab-btn[data-tab="{tab}"]')
        assert btn is not None and btn.is_visible(), f"tab '{tab}' is missing from the nav"
        btn.click()
        page.wait_for_timeout(150)
        assert "active" in (btn.get_attribute("class") or ""), f"tab '{tab}' did not become active"
        exercised.append(tab)

    assert exercised == EXPECTED, f"expected to exercise {EXPECTED}, only did {exercised}"
    assert not page.js_errors, "Uncaught JS errors while exercising tabs:\n" + "\n".join(page.js_errors)
