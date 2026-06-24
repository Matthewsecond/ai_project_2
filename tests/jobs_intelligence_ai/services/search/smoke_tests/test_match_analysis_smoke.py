"""
Live smoke test for the Structured-Outputs candidate-vs-matched-jobs analysis (2.4).

Hits the real API and ASSERTS: a candidate + a set of matched jobs yields a non-empty prose
assessment.

    pytest tests/jobs_intelligence_ai/services/search/smoke_tests -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.search.match_analysis import analyze_candidate_match

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live match-analysis smoke — needs OPENAI_API_KEY"),
]

_CANDIDATE = ("Senior Python developer, 8 years building REST APIs on AWS and PostgreSQL, "
              "based in Vienna. Some Spark exposure but no formal data-engineering role.")

_JOBS = [
    {"title": "Backend Engineer", "company": "ACME", "grade": "A", "score_pct": "88",
     "skills_en": "Python, AWS, PostgreSQL", "city": "Vienna", "state": "Wien",
     "summary": "Build and operate REST APIs."},
    {"title": "Data Engineer", "company": "Globex", "grade": "B", "score_pct": "70",
     "skills_en": "Spark, Airflow, Python", "city": "Linz", "state": "Oberösterreich",
     "summary": "Build large-scale data pipelines."},
]


def test_analyze_candidate_match_live():
    """Live: the assessment comes back as a non-empty prose string."""
    out = analyze_candidate_match(_CANDIDATE, _JOBS)
    assert isinstance(out, str) and out.strip()
