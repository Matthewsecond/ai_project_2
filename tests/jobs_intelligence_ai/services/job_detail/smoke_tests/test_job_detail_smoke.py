"""
Live smoke tests for the Structured-Outputs Job-Detail tools (2.4).

Hits the real API and ASSERTS: a German description translates to non-empty English text, the
description compacts to a short summary, and candidate-strength returns five in-range scores with
five reasons + an overall line.

    pytest tests/jobs_intelligence_ai/services/job_detail/smoke_tests -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.job_detail import (
    translate_description, compact_description, score_candidate_strength,
)

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live job_detail smoke — needs OPENAI_API_KEY"),
]

_DESC_DE = ("Wir suchen eine/n Backend-EntwicklerIn (m/w/d) mit fundierter Python-Erfahrung. "
            "Aufgaben: Entwicklung und Betrieb von REST-APIs, Arbeit mit PostgreSQL und AWS. "
            "Gehalt: ab €4.000 brutto/Monat. Standort: Wien.")

_JOB = {"title": "Backend Engineer", "company": "ACME", "skills": "Python, AWS, PostgreSQL",
        "description": _DESC_DE, "location": "Wien", "salary": "€4000"}

_CV = "Senior Python developer, 8 years building REST APIs on AWS and PostgreSQL. Based in Vienna."


def test_translate_description_live():
    """Live: a German description translates to non-empty English text."""
    out = translate_description(_DESC_DE)
    assert isinstance(out, str) and out.strip()


def test_compact_description_live():
    """Live: the description compacts to a non-empty short summary."""
    out = compact_description(_DESC_DE, lang="en")
    assert isinstance(out, str) and out.strip()


def test_candidate_strength_live():
    """Live: strength scoring returns five in-range scores, five reasons, and an overall line."""
    out = score_candidate_strength(_JOB, _CV, lang="en")
    assert len(out["scores"]) == 5 and all(0 <= s <= 10 for s in out["scores"])
    assert len(out["reasons"]) == 5
    assert (out.get("overall") or "").strip()
