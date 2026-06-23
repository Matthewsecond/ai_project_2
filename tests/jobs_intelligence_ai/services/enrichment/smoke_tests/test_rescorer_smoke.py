"""
Live smoke test for the Structured-Outputs Rescorer (2.3 #2b).

Hits the real API and ASSERTS the structured call works: valid in-range scores for every
job, and that the Python role outscores the truck-driver role for a Python developer.
Catches a misconfigured/rejected structured call — which no mock can see.

    pytest tests/jobs_intelligence_ai/services/enrichment/smoke_tests -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.enrichment import Rescorer

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live rescorer smoke — needs OPENAI_API_KEY"),
]


def test_rescore_live_scores_are_valid_and_sensible():
    """Live: rescore returns one valid in-range grade per job, aligned to the input order,
    and ranks the Python role above the truck-driver role for a Python developer."""
    jobs = [
        {"job_id": 1, "title": "Senior Python Engineer", "skills_en": "Python, Django, PostgreSQL"},
        {"job_id": 2, "title": "Long-haul Truck Driver", "skills_en": "C+E licence, logistics"},
    ]
    out = Rescorer().rescore("Senior Python developer, 8 years, Django/FastAPI.", jobs)

    assert [j["job_id"] for j in out] == [1, 2]          # order preserved
    for j in out:
        assert 0.0 <= j["score"] <= 1.0 and j["grade"] in ("A", "B", "C")
    assert out[0]["score"] > out[1]["score"]             # Python > Truck
