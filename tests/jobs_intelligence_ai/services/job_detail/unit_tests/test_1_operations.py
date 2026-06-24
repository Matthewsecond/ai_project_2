"""
Offline unit tests for the Structured-Outputs Job-Detail tools (2.4).

No network: patch the module's `get_client` so `responses.parse` returns a canned schema object,
or raises. Asserts each prose tool returns the model text and grounds its inputs into the call
(English note only when lang="en"), that candidate-strength comes back as a dict with the 5
dimensions in order, and that no API key / a model error / a null parse all raise (the blueprint
maps those to a 500).
"""
import pytest

import jobs_intelligence_ai.services.job_detail.operations as ops_mod
from jobs_intelligence_ai.services.job_detail import (
    translate_description, compact_description, generate_cv_questions,
    write_outreach, score_candidate_strength,
)
from jobs_intelligence_ai.services.job_detail.config import JobDetailText, CandidateStrength


class _FakeResponses:
    """`.parse()` records kwargs and returns a canned schema object (or raises)."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc, self.calls = parsed, exc, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch(monkeypatch, parsed=None, exc=None):
    responses = _FakeResponses(parsed, exc)
    client = type("C", (), {"responses": responses})()
    monkeypatch.setattr(ops_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(ops_mod.config, "OPENAI_API_KEY", "test-key")
    return responses


_JOB = {"title": "Backend Engineer", "company": "ACME", "skills": "Python, AWS",
        "description": "Build APIs.", "location": "Vienna", "salary": "€4000"}


def test_translate_returns_text(monkeypatch):
    """Translation returns the model text; the description is the model input."""
    resp = _patch(monkeypatch, JobDetailText(text="Translated."))
    out = translate_description("Stellenbeschreibung …")
    assert out == "Translated."
    assert "Stellenbeschreibung" in resp.calls[0]["input"]


def test_compact_english_note_only_when_en(monkeypatch):
    """The 'Respond in English' note is appended only for lang='en'."""
    resp = _patch(monkeypatch, JobDetailText(text="Summary."))
    compact_description("desc", lang="en")
    assert "Respond in English." in resp.calls[0]["instructions"]
    compact_description("desc", lang="de")
    assert "Respond in English." not in resp.calls[1]["instructions"]


def test_cv_questions_grounds_job_and_cv(monkeypatch):
    """The job description and the candidate CV both reach the model input."""
    resp = _patch(monkeypatch, JobDetailText(text="1. ...?"))
    out = generate_cv_questions("Needs Kubernetes.", "10y Python, no k8s.", lang="en")
    assert out == "1. ...?"
    assert "Kubernetes" in resp.calls[0]["input"] and "no k8s" in resp.calls[0]["input"]


def test_outreach_grounds_job_fields(monkeypatch):
    """Outreach grounds the job title/company and the candidate name in the prompt."""
    resp = _patch(monkeypatch, JobDetailText(text="Hi Ann, …"))
    out = write_outreach(_JOB, candidate_name="Ann", cv_text="Senior dev.", lang="en")
    assert out == "Hi Ann, …"
    assert "Backend Engineer" in resp.calls[0]["input"] and "Ann" in resp.calls[0]["input"]


def test_strength_returns_dict_in_order(monkeypatch):
    """Candidate strength returns a dict with the five parallel dimensions and overall."""
    parsed = CandidateStrength(
        axes=["Skills Match", "Experience Level", "Education Fit", "Salary Alignment", "Location Fit"],
        scores=[8, 7, 6, 5, 9],
        reasons=["a", "b", "c", "d", "e"],
        overall="Strong overall fit.")
    resp = _patch(monkeypatch, parsed)
    out = score_candidate_strength(_JOB, "Senior Python dev, Vienna.")
    assert out["scores"] == [8, 7, 6, 5, 9]
    assert out["axes"][0] == "Skills Match" and out["overall"] == "Strong overall fit."
    assert "Backend Engineer" in resp.calls[0]["input"]


def test_no_key_raises(monkeypatch):
    """Without an API key every tool raises (no model call)."""
    monkeypatch.setattr(ops_mod.config, "OPENAI_API_KEY", "")
    with pytest.raises(RuntimeError):
        translate_description("x")
    with pytest.raises(RuntimeError):
        score_candidate_strength(_JOB, "cv")


def test_model_error_propagates(monkeypatch):
    """A model error propagates so the blueprint can report a 500."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        compact_description("desc")


def test_none_parsed_raises(monkeypatch):
    """A null output_parsed raises rather than returning a bad shape."""
    _patch(monkeypatch, parsed=None)
    with pytest.raises(ValueError):
        translate_description("x")
    with pytest.raises(ValueError):
        score_candidate_strength(_JOB, "cv")
