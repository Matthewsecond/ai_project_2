"""
Deeper smoke — actually run a search and open the job-detail modal.

The tabs smoke only does navigation; it never exercises runMatching / renderResults /
openJobModal, so a bug in those paths (e.g. a shared-state migration that collides with a
local `state` variable) sails through it. This test drives the real search flow with the
match endpoint mocked, then opens the modal — covering the search↔modal core that the
2.6c module split touches most.

Run:  pytest tests/jobs_intelligence_ai/frontend/e2e -m e2e -k search
"""
import json

import pytest

pytestmark = pytest.mark.e2e

# Minimal job shaped like a real match result (grade A so it isn't filtered as a weak C).
JOB = {
    "job_id": "J1", "title": "Senior ICU Nurse", "company": "Vienna Clinic",
    "state": "Wien", "city": "Wien", "salary": "€3,200", "grade": "A",
    "score_pct": "92%", "portal": "karriere.at", "posted": "2026-06-20",
    "url": "https://example.com/j1", "match_reason": "Strong skills + location match",
    "lat": 48.20, "lon": 16.37,
}


def test_search_to_modal(logged_in_page):
    page = logged_in_page

    # Force the SSE stream to fail so runMatching falls back to POST /api/match, and
    # mock that with one job. (**/api/match does not match **/api/match/stream.)
    page.route("**/api/match/stream", lambda route: route.abort())
    page.route("**/api/match", lambda route: route.fulfill(
        content_type="application/json",
        body=json.dumps({"ok": True, "jobs": [JOB]}),
    ))

    page.fill("#cvPasteText", "Experienced ICU nurse based in Vienna, German C1, available now.")
    page.click("#btnRun")

    # A result row renders → its title cell carries the open-modal action.
    row = page.wait_for_selector('td[data-action="open-job-modal"]', timeout=8000)
    assert "Senior ICU Nurse" in page.inner_text("#resultsTbody")

    row.click()
    page.wait_for_selector("#jobModal:not(.hidden)", timeout=4000)
    assert page.is_visible("#jobModal"), "job-detail modal did not open"
    assert "Senior ICU Nurse" in page.inner_text("#jobModal")

    assert not page.js_errors, "Uncaught JS errors during search→modal:\n" + "\n".join(page.js_errors)
