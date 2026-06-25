"""
Smoke test — log in, visit every tab, assert nothing threw.

This is the safety net for the 2.6c module split: if a module fails to load or calls a function
that wasn't imported, exercising its tab raises an uncaught exception, which `pageerror` records.

Nav model in index.html: a top "mode toggle" (Candidate / Analytics) gates two groups of tabs —
`data-mode-group="search"` (search, saved) and `data-mode-group="analytics"` (radar, map,
analytics-summary, hidden until you switch to Analytics mode). The smoke drives that real nav.

Run just this suite:  pytest tests/jobs_intelligence_ai/frontend/e2e -m e2e
"""
import pytest

pytestmark = pytest.mark.e2e

# (mode toggle, [tabs revealed in that mode]) — the conftest forces all feature flags on.
MODES = [
    ("search",    ["search", "saved"]),
    ("analytics", ["radar", "map", "analytics-summary"]),
]
EXPECTED = [tab for _, tabs in MODES for tab in tabs]


def test_tabs_smoke(logged_in_page):
    page = logged_in_page

    exercised = []
    for mode, tabs in MODES:
        toggle = page.query_selector(f'.mode-toggle-btn[data-mode="{mode}"]')
        if toggle and toggle.is_visible():
            toggle.click()
            page.wait_for_timeout(150)
        for tab in tabs:
            btn = page.query_selector(f'.tab-btn[data-tab="{tab}"]')
            if btn is None or not btn.is_visible():
                continue  # feature-flagged off
            btn.click()
            page.wait_for_timeout(150)
            assert "active" in (btn.get_attribute("class") or ""), f"tab '{tab}' did not become active"
            exercised.append(tab)

    assert exercised == EXPECTED, f"expected to exercise {EXPECTED}, only did {exercised}"
    assert not page.js_errors, "Uncaught JS errors while exercising tabs:\n" + "\n".join(page.js_errors)
