"""
Live smoke test for the Structured-Outputs grader (Stage 2.1b).

Unlike the mocked unit tests, this hits the REAL API and ASSERTS the structured call
actually works: that `responses.parse(text_format=_Scores)` returns valid, in-range
scores for every job, and that a clear-cut candidate outscores an obvious mismatch.
This is what catches "structured outputs is misconfigured / rejected" — a thing no
mock can see.

Live + marked smoke (excluded by default). Run:
    pytest tests/jobs_intelligence_ai/search/smoke_tests/test_grader_smoke.py -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.search.config import GraderConfig
from jobs_intelligence_ai.search.grader import Grader
from jobs_intelligence_ai.shared.llm import get_client

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live grader smoke — needs OPENAI_API_KEY"),
]


def test_grader_live_scores_are_valid_and_sensible():
    jobs = [
        {"title": "Senior Python Engineer", "company": "Acme", "skills": "Python, Django, PostgreSQL"},
        {"title": "Long-haul Truck Driver", "company": "Transco", "skills": "C+E licence, logistics"},
    ]
    candidate = "Senior Python developer, 8 years, Django/FastAPI/PostgreSQL, Bratislava."

    out = Grader(get_client(), GraderConfig()).grade(candidate, jobs)

    # The structured call must return one valid grade per job — proves it WORKED.
    assert len(out) == len(jobs)
    for j in out:
        assert 0.0 <= j["score"] <= 1.0
        assert j["grade"] in ("A", "B", "C")
        assert j["match_reason"].strip()          # a real reason came back

    # Sanity: the Python role must outscore the truck-driver role for a Python dev.
    assert out[0]["score"] > out[1]["score"], (
        f"expected Python > Truck, got {out[0]['score']} vs {out[1]['score']}"
    )
