"""
Live smoke test for the Structured-Outputs quality classifier (2.3 #2e).

Hits the real API and ASSERTS the structured call works: every job comes back with a valid
quality / fit / score / flags set (the Literal-constrained schema is enforced). Group stats
are stubbed so this needs no DB — only the API.

    pytest tests/jobs_intelligence_ai/services/enrichment/smoke_tests -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.enrichment import classify_quality

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live quality smoke — needs OPENAI_API_KEY"),
]

_GROUP = {"occ_group": "IT", "count": 50, "mean": 4000.0, "median": 3900.0, "p25": 3300.0, "p75": 4600.0}


def test_quality_live_assessment_is_valid():
    """Live: each job gets a schema-valid quality assessment, and a senior role asking
    a lot for a tiny salary is not rated 'high'."""
    jobs = [
        {"title": "Senior Software Architect", "salary": "2300",
         "description": "Lead architecture, 8+ years, own the platform, manage a team.", "skills_en": "Java, AWS, Kafka"},
        {"title": "Junior Developer", "salary": "2200",
         "description": "Entry-level role, mentorship provided, full description and contact.", "skills_en": "Python"},
    ]
    out = classify_quality(jobs, _GROUP)
    for j in out:
        assert j["quality"] in ("high", "mid", "low")
        assert j["quality_fit"] in ("overpaying", "fair", "underpaying", "unknown")
        assert 0.0 <= j["quality_score"] <= 1.0
        assert isinstance(j["quality_flags"], list)
    # the underpaid senior architect should not come out "high"
    assert out[0]["quality"] in ("mid", "low")
