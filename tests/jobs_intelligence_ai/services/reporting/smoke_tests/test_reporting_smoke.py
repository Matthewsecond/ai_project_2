"""
Live smoke tests for the Structured-Outputs reporting calls (2.3 #4).

Hits the real API and ASSERTS the structured calls work: the opportunity briefing returns
all expected sections from a snapshot, the filter suggestion stays within the provided
option lists, and the session-report elaboration returns one section per saved insight.

    pytest tests/jobs_intelligence_ai/services/reporting/smoke_tests -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.reporting import (
    generate_briefing, suggest_filters, elaborate_items,
)

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live reporting smoke — needs OPENAI_API_KEY"),
]

_SECTORS = [{"occ_group": "IT & Software", "total_jobs": 420, "avg_days_in_system": 12,
             "stale_30": 30, "stale_60": 8, "urgent_deadline": 15, "avg_salary": 3800}]
_STATES = [{"state": "Wien", "total_jobs": 600, "avg_days_in_system": 14,
            "stale_30": 40, "urgent_deadline": 20, "avg_salary": 3500}]
_PORTALS = [{"portal": "karriere.at", "total_jobs": 500, "avg_days_in_system": 15,
             "stale_60": 12, "avg_salary": 3400}]
_TREND = [{"year_week": "2026-24", "week_start": "2026-06-08", "jobs_created": 120}]
_TOTALS = {"total_active": 1000, "stale_30": 200, "stale_60": 60, "urgent_14d": 35,
           "sector_count": 1, "state_count": 1}


def test_generate_briefing_live():
    """Live: returns a briefing with a headline and all list sections present."""
    out = generate_briefing(_SECTORS, _STATES, _PORTALS, _TREND, _TOTALS)
    assert out["headline"].strip()
    for key in ("top_opportunities", "underserved", "urgency_alerts", "recommendations"):
        assert isinstance(out[key], list)
    assert out["recommendations"]               # at least one concrete recommendation


def test_suggest_filters_live_stays_in_options():
    """Live: the suggested occ_groups are a subset of the provided sectors."""
    sectors = ["IT & Software", "Finance & Accounting", "Healthcare & Nursing"]
    out = suggest_filters("software engineering roles", sectors, ["Wien"], ["karriere.at"])
    assert set(out["occ_groups"]) <= set(sectors)
    assert out["explanation"].strip()


def test_elaborate_items_live():
    """Live: each saved insight comes back with a heading and elaboration."""
    items = [{"type": "opportunity", "label": "IT surge", "content": "IT roles up 20% in Vienna."},
             {"type": "trend", "label": "Finance cooling", "content": "Finance postings down 10%."}]
    out = elaborate_items(items, context={"totals": _TOTALS, "headline": "Hot IT market"})
    assert len(out) == 2
    assert all(o["heading"].strip() and o["elaboration"].strip() for o in out)
