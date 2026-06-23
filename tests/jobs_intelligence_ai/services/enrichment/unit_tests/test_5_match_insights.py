"""
Offline unit test for build_insights (2.3 #2 — match_insights).

match_insights has NO LLM call (pure assembly + optional DB market lookup), so there's
nothing to convert to Structured Outputs. With saved jobs that carry no occ_group the DB
lookup is skipped entirely, so we can verify the core aggregation fully offline.
"""
from datetime import date

from jobs_intelligence_ai.services.enrichment import build_insights

_TODAY = date(2026, 6, 23)
# No occ_group on any job → _group_market() is never called → no DB.
_JOBS = [
    {"grade": "A", "score": 0.9, "salary": "3000", "state": "Wien"},
    {"grade": "B", "score": 0.7, "salary": "2500", "state": "Wien"},
    {"grade": "C", "score": 0.4, "salary": "2000"},
]
_PROFILE = {"name": "Petra Test", "title": "Engineer",
            "skills": ["Python", "SQL"], "salary_expectation": "2400-3200"}


def test_aggregates_grades_strength_and_market():
    """Core aggregates from the saved jobs: counts, grade breakdown, mean-score strength,
    and (no market rows → from the jobs' own salaries) the salary band/positioning."""
    d = build_insights("ignored", _JOBS, _PROFILE, today=_TODAY)
    assert d["name"] == "Petra Test"
    assert d["matches"] == 3
    assert d["grades"] == {"A": 1, "B": 1, "C": 1}
    assert d["strength"] == 67                       # round(mean(0.9,0.7,0.4) * 100)
    assert d["market"]["median"] == 2500             # from job salaries (no DB market)
    assert d["candBand"] == [2400, 3200]             # parsed from salary_expectation
    assert "covers 67% of roles" in d["salaryStat"]["overlap"]   # 2 of 3 in band


def test_payload_has_dashboard_sections():
    """The payload carries the sections the Saved dashboard / PDF render from."""
    d = build_insights("ignored", _JOBS, _PROFILE, today=_TODAY)
    for key in ("market", "salaryStat", "skills2", "gaps", "radar", "priority"):
        assert key in d
    assert len(d["radar"]) == 6                      # the 6 fit axes


def test_empty_jobs_is_safe():
    """No saved jobs → a valid skeleton payload, no crash, no DB."""
    d = build_insights("Nobody", [], None, today=_TODAY)
    assert d["matches"] == 0 and d["grades"] == {"A": 0, "B": 0, "C": 0}
