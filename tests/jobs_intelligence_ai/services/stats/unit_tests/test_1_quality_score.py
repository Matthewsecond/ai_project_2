"""
Offline unit tests for the pure job-quality signals (stats.quality_score).

These take a plain job dict (and, for salary, precomputed group stats) and return
deterministic signals — no DB, no network. Imported via the package public API.
"""
from datetime import date, timedelta

from jobs_intelligence_ai.services.stats import (
    completeness_score, salary_signal, employment_signals,
    freshness_signal, description_complexity, build_quality_context,
)

# group stats reused across the salary-band cases (count>0 so it's not "unknown")
_GROUP = {"count": 100, "mean": 3000.0, "median": 2900.0, "p25": 2500.0, "p75": 3500.0}


def test_completeness_full_partial_empty():
    """All weighted fields present → 1.0; none → 0.0; only description (weight 3 of 10) → 0.3."""
    full = {"description": "d", "skills_en": "s", "salary": "1", "url": "u",
            "contacts": "c", "city": "Wien"}
    assert completeness_score(full) == 1.0
    assert completeness_score({}) == 0.0
    assert completeness_score({"description": "d"}) == 0.3


def test_salary_signal_bands():
    """A salary maps to the right quartile band relative to the group stats."""
    assert salary_signal({"salary": "2000"}, _GROUP)["band"] == "below_p25"
    assert salary_signal({"salary": "2700"}, _GROUP)["band"] == "p25_median"
    assert salary_signal({"salary": "3000"}, _GROUP)["band"] == "median_p75"
    assert salary_signal({"salary": "4000"}, _GROUP)["band"] == "above_p75"


def test_salary_signal_unknown_when_no_data_or_no_salary():
    """No group data, or a missing/zero salary, yields the 'unknown' band."""
    assert salary_signal({"salary": "3000"}, {"count": 0})["band"] == "unknown"
    assert salary_signal({"salary": "0"}, _GROUP)["band"] == "unknown"


def test_salary_signal_vs_mean_pct():
    """vs_mean_pct is the signed % distance from the group mean (3300 vs 3000 → +10%)."""
    assert salary_signal({"salary": "3300"}, _GROUP)["vs_mean_pct"] == 10.0


def test_employment_signals_flags():
    """Keyword matching on the German employment/work-time fields sets the right flags.

    NOTE: uses 'Festanstellung' (not 'unbefristet') because of a known pre-existing quirk —
    'unbefristet' contains the substring 'befristet', so it wrongly trips is_temp. Tracked
    as a bug to fix separately; this test pins the clean, intended behavior."""
    sig = employment_signals({"employment_relationship": "Festanstellung, Vollzeit",
                              "work_time": "Vollzeit", "education": "Matura"})
    assert sig["is_permanent"] and sig["is_fulltime"] and sig["has_education_req"]
    assert not sig["is_parttime"] and not sig["is_temp"]


def test_freshness_recent_vs_deadline_passed():
    """A recently-posted job scores high freshness; a past deadline is flagged passed.

    NOTE: posted 10 days ago (not 0) — pre-existing quirk: `days_old or 30` treats a
    posted-today (days_old==0) job as 30 days old. Tracked as a bug to fix separately."""
    today = date.today()
    fresh = freshness_signal({"posted": (today - timedelta(days=10)).isoformat()})
    assert fresh["days_old"] == 10 and 0.85 < fresh["freshness_score"] < 0.9
    assert not fresh["deadline_passed"]
    stale = freshness_signal({"posted": (today - timedelta(days=120)).isoformat(),
                              "application_deadline": (today - timedelta(days=1)).isoformat()})
    assert stale["deadline_passed"] and stale["freshness_score"] == 0.0


def test_description_complexity_leadership_and_years():
    """Heuristics pick up leadership language and a required-years figure from the text."""
    sig = description_complexity({"description": "Sie übernehmen die Leitung. 5 Jahre Erfahrung."})
    assert sig["has_leadership"] is True
    assert sig["required_years"] == 5


def test_build_quality_context_bundles_all_signals():
    """The bundle the AI classifier receives carries every signal group."""
    ctx = build_quality_context({"description": "d", "salary": "3000"}, _GROUP)
    assert set(ctx) == {"completeness", "salary_signal", "employment",
                        "freshness", "description_signals"}
