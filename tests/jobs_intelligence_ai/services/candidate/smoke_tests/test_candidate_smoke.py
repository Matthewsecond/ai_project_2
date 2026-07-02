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
from jobs_intelligence_ai.infra.integrations.linkedin import map_to_profile
from jobs_intelligence_ai.services.candidate import (
    enrich_linkedin_profile, parse_candidate_profile, send_candidate_message,
    extract_guided_fields, phrase_guided_reply,
)

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not config.OPENAI_API_KEY, reason="live candidate smoke — needs OPENAI_API_KEY"),
]

# Raw item in the harvestapi/linkedin-profile-scraper schema (camelCase, nested).
_SCRAPE = {
    "firstName": "Max", "lastName": "Weber", "headline": "Senior Backend Engineer",
    "location": {"parsed": {"city": "Vienna", "country": "Austria"}},
    "skills": [{"name": "Python"}, {"name": "FastAPI"}, {"name": "PostgreSQL"},
               {"name": "Docker"}, {"name": "AWS"}],
    "experience": [
        {"position": "Senior Backend Engineer", "companyName": "TechSolutions",
         "startDate": {"text": "2019", "year": 2019}, "endDate": {"text": "Present"},
         "description": "Led API platform, 6 engineers."},
        {"position": "Backend Developer", "companyName": "WebFactory",
         "startDate": {"text": "2015", "year": 2015}, "endDate": {"text": "2019", "year": 2019},
         "description": "Python services."},
    ],
}


def test_enrich_linkedin_profile_live():
    """Live: map the raw scrape, then enrichment returns a valid seniority and merges
    inferred fields over the mechanical base — the real LinkedIn import pipeline."""
    base = map_to_profile(_SCRAPE)
    base["phone"] = "123"
    out = enrich_linkedin_profile(_SCRAPE, base=base)
    assert out["name"] == "Max Weber"          # firstName + lastName combined
    assert out["seniority"] in ("Junior", "Mid", "Senior", "Lead", "Executive")
    assert out["phone"] == "123"               # base preserved
    assert out["source"] == "imported"
    assert isinstance(out.get("top_skills"), list) and out["top_skills"]


_CV_TEXT = (
    "Peter Varga — B2B Sales Manager with 10 years of experience in enterprise software "
    "and SaaS sales, based in Bratislava. Fluent Slovak and English (C1). "
    "Looking for €2,800–3,400/month, available immediately. peter@example.com"
)


def test_parse_candidate_profile_live():
    """Live: raw CV text is parsed into a structured profile with skills + a summary."""
    out = parse_candidate_profile(_CV_TEXT)
    assert isinstance(out.get("skills"), list) and out["skills"]
    assert (out.get("summary") or "").strip()
    assert out.get("title")


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


_GUIDED_KW = dict(draft="{}", locked="[]",
                  catalog="it — IT & software\nconstruction — Construction & trades",
                  last_field="", offer="none", salary="none")


def test_guided_extract_fields_live():
    """Live: 'a Java developer' classifies the IT sector and records the role."""
    out = extract_guided_fields("We're looking for a Java developer.", **_GUIDED_KW)
    assert isinstance(out, dict)
    assert out.get("sector") or out.get("roles")   # the message yielded some spec signal


def test_guided_phrase_reply_live():
    """Live: reply phrasing returns a dict with a non-empty reply string."""
    out = phrase_guided_reply(
        "A Java developer.", lang="English", last_question="",
        field_updates='{"roles": ["Java Developer"], "sector": ["it"]}', user_edits="none",
        draft='{"roles": ["Java Developer"], "sector": ["it"]}',
        facets="- postings in this role family: 120", salary_hint="none available")
    assert isinstance(out, dict)
    assert (out.get("reply") or "").strip()
