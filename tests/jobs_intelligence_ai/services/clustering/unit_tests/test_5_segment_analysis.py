"""
Offline unit tests for the Structured-Outputs segment analysis calls (2.4).

No network: patch the module's `get_client` so `responses.parse` returns a canned schema
object, or raises. Asserts segment_overview returns the prose text and grades come back in
input order as dicts, that the inputs are grounded into the prompt, and that no API key / a
model error raises (the blueprint maps those to a 500).
"""
import pytest

import jobs_intelligence_ai.services.clustering.segment_analysis as sa_mod
from jobs_intelligence_ai.services.clustering import segment_overview, grade_candidates_for_job
from jobs_intelligence_ai.services.clustering.config import (
    SegmentOverview, CandidateGrades, _CandidateGrade,
)


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
    monkeypatch.setattr(sa_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(sa_mod.config, "OPENAI_API_KEY", "test-key")
    return responses


def test_segment_overview_returns_text(monkeypatch):
    """The parsed SegmentOverview.text is returned; segment names land in the prompt."""
    resp = _patch(monkeypatch, SegmentOverview(text="Focus on the sellers segment."))
    out = segment_overview([{"title": "SaaS sellers", "candidates": 3, "ab_jobs": 10,
                             "total_jobs": 12, "summary": "Senior AEs"}])
    assert out == "Focus on the sellers segment."
    assert "SaaS sellers" in resp.calls[0]["input"]


def test_grade_candidates_returns_ordered_dicts(monkeypatch):
    """Grades come back as dicts in input order; the job + candidates ground the prompt."""
    parsed = CandidateGrades(candidates=[
        _CandidateGrade(score=0.8, reason="Strong match."),
        _CandidateGrade(score=0.3, reason="Weak match."),
    ])
    resp = _patch(monkeypatch, parsed)
    out = grade_candidates_for_job(
        {"title": "Account Executive", "company": "ACME"},
        [{"name": "Ann", "text": "AE 9y"}, {"name": "Bob", "text": "Junior SDR"}],
    )
    assert [g["score"] for g in out] == [0.8, 0.3]
    assert out[0]["reason"] == "Strong match."
    assert "Account Executive" in resp.calls[0]["input"] and "Ann" in resp.calls[0]["input"]


def test_no_key_raises(monkeypatch):
    """Without an API key both calls raise (no model call)."""
    monkeypatch.setattr(sa_mod.config, "OPENAI_API_KEY", "")
    with pytest.raises(RuntimeError):
        segment_overview([])
    with pytest.raises(RuntimeError):
        grade_candidates_for_job({"title": "x"}, [{"name": "Ann", "text": "y"}])


def test_model_error_propagates(monkeypatch):
    """A model error propagates so the blueprint can report it."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        segment_overview([{"title": "x"}])


def test_none_parsed_raises(monkeypatch):
    """A null output_parsed raises rather than returning a bad shape."""
    _patch(monkeypatch, parsed=None)
    with pytest.raises(ValueError):
        grade_candidates_for_job({"title": "x"}, [{"name": "Ann", "text": "y"}])
