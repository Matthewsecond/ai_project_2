"""
Offline unit tests for report_pipeline (2.3 #4 — Candidate Pipeline / Match Insights PDFs).

report_pipeline is a pure reportlab renderer (NO LLM call), so there's nothing to convert —
these just exercise both public entry points end-to-end and assert they emit a real PDF.
The insights payload is produced by the real (pure, offline) enrichment.build_insights.
"""
from datetime import date

from jobs_intelligence_ai.services.reporting import (
    generate_insights_pdf, generate_saved_jobs_pdf,
)
from jobs_intelligence_ai.services.enrichment import build_insights

# No occ_group on any job → build_insights skips its DB market lookup → fully offline.
_JOBS = [
    {"candidate_name": "Petra Test", "title": "Data Engineer", "company": "ACME",
     "grade": "A", "score": 0.9, "salary": "3000", "state": "Wien", "extras": {}},
    {"candidate_name": "Petra Test", "title": "Analyst", "company": "Globex",
     "grade": "B", "score": 0.7, "salary": "2500", "state": "Wien", "extras": {}},
]
_PROFILE = {"name": "Petra Test", "title": "Engineer", "skills": ["Python", "SQL"],
            "salary_expectation": "2400-3200"}


def test_saved_jobs_pdf_emits_a_pdf():
    """The Candidate Pipeline Report renders to non-empty PDF bytes."""
    pdf = generate_saved_jobs_pdf(_JOBS, candidate_profile=_PROFILE)
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000


def test_insights_pdf_emits_a_pdf():
    """A real build_insights payload renders to non-empty PDF bytes."""
    payload = build_insights("Petra Test", _JOBS, _PROFILE, today=date(2026, 6, 23))
    pdf = generate_insights_pdf(payload)
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000
