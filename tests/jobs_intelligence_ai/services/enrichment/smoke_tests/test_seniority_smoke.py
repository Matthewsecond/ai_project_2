"""
Live smoke test for the Structured-Outputs seniority classifier (2.3 #2d).

Hits the real API and ASSERTS the structured call works: a clearly-senior posting is
classified "senior" and a clearly-junior one "junior", with every job tagged a valid level.

    pytest tests/jobs_intelligence_ai/services/enrichment/smoke_tests -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.enrichment import classify_seniority

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live seniority smoke — needs OPENAI_API_KEY"),
]


def test_seniority_live_classifies_clear_cases():
    """Live: a Head-of role → senior; an intern → junior; all jobs get a valid level."""
    jobs = [
        {"title": "Head of Engineering", "description": "Lead the engineering org, 10+ years, set architecture and strategy."},
        {"title": "Marketing Intern", "description": "Entry-level internship for a student, no prior experience required."},
    ]
    classify_seniority(jobs)
    assert all(j["seniority"] in ("senior", "mid", "junior") for j in jobs)
    assert jobs[0]["seniority"] == "senior"
    assert jobs[1]["seniority"] == "junior"
