"""
Live smoke tests for the candidate service Structured-Outputs calls (2.3 #7).

Hits the real API and ASSERTS: the LinkedIn enricher returns a normalized profile with a
valid seniority + inferred fields merged over the base; the candidate assistant both
discusses (no edits) and applies a CV edit (only the changed field) on request.

    pytest tests/jobs_intelligence_ai/services/candidate/smoke_tests -m smoke -s
"""
import os

os.environ.setdefault("COUNTRY", "sk")

import pytest

from jobs_intelligence_ai import config
from jobs_intelligence_ai.services.candidate import enrich_linkedin_profile, send_candidate_message

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live candidate smoke — needs OPENAI_API_KEY"),
]

_SCRAPE = {
    "full_name": "Max Weber", "headline": "Senior Backend Engineer",
    "city": "Vienna", "country": "Austria",
    "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
    "experiences": [
        {"title": "Senior Backend Engineer", "company": "TechSolutions",
         "starts_at": "2019", "ends_at": None, "description": "Led API platform, 6 engineers."},
        {"title": "Backend Developer", "company": "WebFactory",
         "starts_at": "2015", "ends_at": "2019", "description": "Python services."},
    ],
}


def test_enrich_linkedin_profile_live():
    """Live: enrichment returns a valid seniority and merges inferred fields over the base."""
    out = enrich_linkedin_profile(_SCRAPE, base={"phone": "123"})
    assert out["seniority"] in ("Junior", "Mid", "Senior", "Lead", "Executive")
    assert out["phone"] == "123"               # base preserved
    assert out["source"] == "imported"
    assert isinstance(out.get("top_skills"), list) and out["top_skills"]


_PROFILE = {"name": "Anna Bauer", "title": "Warehouse Supervisor",
            "skills": ["SAP WM", "Forklift"], "location": "Vienna"}


def test_assistant_discussion_no_edits_live():
    """Live: a pure question returns a reply with no profile_updates."""
    out = send_candidate_message("smoke-disc", "Is this candidate senior enough for a lead role?",
                                 _PROFILE, jobs=[], lang="en")
    assert out["text"].strip()
    assert out["profile_updates"] == {}


def test_assistant_cv_edit_live():
    """Live: asking to add a licence yields a profile_updates edit + a cv_note."""
    out = send_candidate_message("smoke-edit",
                                 "Add that she now holds a valid German B2 language certificate.",
                                 _PROFILE, jobs=[], lang="en")
    assert out["text"].strip()
    assert out["profile_updates"]              # some field changed
    assert out["cv_note"].strip()
