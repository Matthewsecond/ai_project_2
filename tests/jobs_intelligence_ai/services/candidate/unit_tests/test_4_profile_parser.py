"""
Offline unit tests for the Structured-Outputs CV-text profile parser (2.4).

No network: patch the module's `get_client` so `responses.parse` returns a canned
`CandidateProfile`, or raises. Asserts the parsed fields come back as a dict, that a missing
key raises, and that no API key raises (the blueprint turns those into error responses).
"""
import pytest

import jobs_intelligence_ai.services.candidate.profile_parser as pp_mod
from jobs_intelligence_ai.services.candidate import parse_candidate_profile
from jobs_intelligence_ai.services.candidate.config import CandidateProfile


class _FakeResponses:
    """`.parse()` returns a canned CandidateProfile (as output_parsed), or raises."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch(monkeypatch, parsed=None, exc=None):
    client = type("C", (), {"responses": _FakeResponses(parsed, exc)})()
    monkeypatch.setattr(pp_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(pp_mod.config, "OPENAI_API_KEY", "test-key")


def _profile(**over):
    """A fully-populated CandidateProfile, with per-test overrides."""
    base = dict(
        name="Peter Varga", title="B2B Sales Manager", seniority="Senior",
        experience_years="10 years",
        skills=["B2B Sales", "SaaS", "Enterprise"], location="Bratislava",
        languages="Slovak (native), English C1", salary_expectation="€2,800–3,400/month",
        availability="Immediately", email="peter@example.com", phone="+421900000000",
        linkedin="https://linkedin.com/in/peter", summary="Experienced B2B sales manager.")
    base.update(over)
    return CandidateProfile(**base)


def test_parses_profile_to_dict(monkeypatch):
    """A canned CandidateProfile comes back as a plain dict with all fields."""
    _patch(monkeypatch, _profile(title="Sales Director"))
    out = parse_candidate_profile("Peter Varga, sales director, 10 years…")
    assert out["title"] == "Sales Director"
    assert out["skills"] == ["B2B Sales", "SaaS", "Enterprise"]
    assert out["name"] == "Peter Varga"


def test_no_key_raises(monkeypatch):
    """Without an API key the parser raises (no model call)."""
    monkeypatch.setattr(pp_mod.config, "OPENAI_API_KEY", "")
    with pytest.raises(RuntimeError):
        parse_candidate_profile("some text")


def test_none_parsed_raises(monkeypatch):
    """A null output_parsed raises rather than returning a bad shape."""
    _patch(monkeypatch, parsed=None)
    with pytest.raises(ValueError):
        parse_candidate_profile("some text")


def test_model_error_propagates(monkeypatch):
    """A model error propagates so the blueprint can report it."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        parse_candidate_profile("some text")
