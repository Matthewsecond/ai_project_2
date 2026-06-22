"""
Pin the CURRENT behavior of the LLM-response JSON extractors before they are
unified into shared/json.py (Stage 2.1b).

Imports use the present canonical locations; in 2.1b these become shims that
delegate to shared/json.py, so these same assertions then prove the merge is
behavior-preserving. The asserts must NOT change across the move.
"""
from jobs_intelligence_ai.search.utils import parse_json
from jobs_intelligence_ai.chat import _parse, _parse_candidate

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


# ── _parse: object with "jobs" (chat search) ────────────────────────────────────
def test_parse_jobs_fenced():
    out = _parse(samples.LLM_JOBS_FENCED)
    assert out["text"] == "Found 2 roles."
    assert [j["job_id"] for j in out["jobs"]] == ["1", "2"]


def test_parse_jobs_bare():
    out = _parse(samples.LLM_JOBS_BARE)
    assert out["text"] == ""
    assert out["jobs"] == [{"job_id": "1", "title": "Engineer"}]


def test_parse_no_jobs():
    out = _parse("Sorry, nothing matched.")
    assert out == {"text": "Sorry, nothing matched.", "jobs": []}


# ── _parse_candidate: object with "profile_updates" (candidate chat) ────────────
def test_parse_candidate_profile_update():
    out = _parse_candidate(samples.LLM_PROFILE_FENCED)
    assert out["text"] == "Added the licence."
    assert out["profile_updates"] == {"skills": ["forklift"]}
    assert out["cv_note"] == "Holds a forklift licence."


def test_parse_candidate_no_update():
    out = _parse_candidate("Just discussing, no change.")
    assert out == {"text": "Just discussing, no change.", "profile_updates": {}, "cv_note": ""}
