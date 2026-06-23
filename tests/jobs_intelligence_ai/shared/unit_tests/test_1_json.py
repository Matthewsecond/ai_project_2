"""
Pin the CURRENT behavior of the LLM-response JSON extractors before they are
unified into shared/json.py (Stage 2.1b).

Imports use the present canonical locations; in 2.1b these become shims that
delegate to shared/json.py, so these same assertions then prove the merge is
behavior-preserving. The asserts must NOT change across the move.
"""
from jobs_intelligence_ai.services.search.utils import parse_json
from jobs_intelligence_ai.chat import _parse_candidate

from tests._fixtures import samples


# ── parse_json: array shape (retrieval ids / lists) ─────────────────────────────
def test_parse_json_fenced_array():
    assert parse_json(samples.LLM_ARRAY_FENCED) == [12345, 67890]


def test_parse_json_bare_array():
    assert parse_json(samples.LLM_ARRAY_BARE) == [12345, 67890]


def test_parse_json_array_embedded_in_prose():
    assert parse_json(samples.LLM_ARRAY_WITH_PROSE) == [12345, 67890]


def test_parse_json_empty_returns_empty_list():
    assert parse_json("") == []
    assert parse_json("no json here") == []


def test_parse_json_strips_citation_markers():
    out = parse_json(samples.LLM_ARRAY_WITH_CITATIONS)
    assert out == [{"title": "Engineer"}]


# Note: the job-search chat `_parse` (object with "jobs") was deleted in rework 2.3 #5
# (the conversational job-search feature was superseded); its cases were removed here.


# ── _parse_candidate: object with "profile_updates" (candidate chat) ────────────
def test_parse_candidate_profile_update():
    out = _parse_candidate(samples.LLM_PROFILE_FENCED)
    assert out["text"] == "Added the licence."
    assert out["profile_updates"] == {"skills": ["forklift"]}
    assert out["cv_note"] == "Holds a forklift licence."


def test_parse_candidate_no_update():
    out = _parse_candidate("Just discussing, no change.")
    assert out == {"text": "Just discussing, no change.", "profile_updates": {}, "cv_note": ""}
