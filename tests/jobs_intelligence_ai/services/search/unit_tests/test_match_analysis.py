"""
Offline unit tests for the Structured-Outputs candidate-vs-matched-jobs analysis (2.4).

No network: patch the module's `get_client` so `responses.parse` returns a canned `MatchAnalysis`,
or raises. Asserts the prose text is returned, that the candidate profile + matched jobs are
grounded into the model input, and that no API key / a model error / a null parse all raise (the
blueprint maps those to a 500).
"""
import pytest

import jobs_intelligence_ai.services.search.match_analysis as ma_mod
from jobs_intelligence_ai.services.search.match_analysis import analyze_candidate_match
from jobs_intelligence_ai.services.search.config import MatchAnalysis


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
    monkeypatch.setattr(ma_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(ma_mod.config, "OPENAI_API_KEY", "test-key")
    return responses


_JOBS = [
    {"title": "Backend Engineer", "company": "ACME", "grade": "A", "score_pct": "88",
     "skills": "Python, AWS", "city": "Vienna", "state": "Wien"},
    {"title": "Data Engineer", "company": "Globex", "grade": "B", "score_pct": "72",
     "skills": "Spark", "summary": "Build pipelines."},
]


def test_returns_text(monkeypatch):
    """The parsed MatchAnalysis.text is returned."""
    _patch(monkeypatch, MatchAnalysis(text="Strong across backend roles."))
    out = analyze_candidate_match("Senior Python dev.", _JOBS)
    assert out == "Strong across backend roles."


def test_grounds_profile_and_jobs(monkeypatch):
    """The candidate profile and the matched jobs land in the model input."""
    resp = _patch(monkeypatch, MatchAnalysis(text="ok"))
    analyze_candidate_match("Senior Python dev, Vienna.", _JOBS)
    sent = resp.calls[0]["input"]
    assert "Senior Python dev" in sent
    assert "Backend Engineer" in sent and "Data Engineer" in sent


def test_no_key_raises(monkeypatch):
    """Without an API key the call raises (no model call)."""
    monkeypatch.setattr(ma_mod.config, "OPENAI_API_KEY", "")
    with pytest.raises(RuntimeError):
        analyze_candidate_match("x", _JOBS)


def test_model_error_propagates(monkeypatch):
    """A model error propagates so the blueprint can report a 500."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        analyze_candidate_match("x", _JOBS)


def test_none_parsed_raises(monkeypatch):
    """A null output_parsed raises rather than returning a bad shape."""
    _patch(monkeypatch, parsed=None)
    with pytest.raises(ValueError):
        analyze_candidate_match("x", _JOBS)
