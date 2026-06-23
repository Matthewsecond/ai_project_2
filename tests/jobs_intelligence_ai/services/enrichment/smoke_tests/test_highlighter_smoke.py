"""
Live smoke test for the Structured-Outputs Highlighter (2.3 #2c).

Hits the real API and ASSERTS the structured call works: given a clear criterion, it
returns the id of the job that matches and not the one that doesn't.

    pytest tests/jobs_intelligence_ai/services/enrichment/smoke_tests -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.enrichment import Highlighter

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live highlighter smoke — needs OPENAI_API_KEY"),
]


def test_highlight_live_selects_the_matching_job():
    """Live: the criterion 'requires Python' highlights the Python job, not the sales job."""
    jobs = [
        {"job_id": "py", "title": "Backend Engineer", "skills_en": "Python, Django, PostgreSQL"},
        {"job_id": "sales", "title": "Sales Manager", "skills_en": "B2B sales, CRM, negotiation"},
    ]
    out = Highlighter().highlight("roles that require Python", jobs)
    assert "py" in out
    assert "sales" not in out
