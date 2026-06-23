"""
Offline unit tests for the Structured-Outputs seniority classifier (2.3 #2d).

No network: patch the module's `get_client` so `responses.parse` returns a canned
`SeniorityResults`. Asserts the AI levels are applied, unclassified jobs fall back to the
keyword guess, and an API failure / missing key degrades to the pure keyword heuristic.
"""
import jobs_intelligence_ai.services.enrichment.seniority_classifier as sen_mod
from jobs_intelligence_ai.services.enrichment.seniority_classifier import (
    classify_seniority, _keyword_guess,
)
from jobs_intelligence_ai.services.enrichment.config import SeniorityResults, _Seniority


class _FakeResponses:
    """`.parse()` returns a canned SeniorityResults (mimicking output_parsed), or raises."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch_client(monkeypatch, parsed=None, exc=None):
    client = type("C", (), {"responses": _FakeResponses(parsed, exc)})()
    monkeypatch.setattr(sen_mod, "get_client", lambda *a, **k: client)


def test_applies_model_levels(monkeypatch):
    """The model's (index, level) pairs are written onto the matching jobs."""
    _patch_client(monkeypatch, SeniorityResults(items=[
        _Seniority(i=0, level="senior"), _Seniority(i=1, level="junior")]))
    jobs = [{"title": "Backend role"}, {"title": "Some role"}]
    classify_seniority(jobs)
    assert jobs[0]["seniority"] == "senior" and jobs[1]["seniority"] == "junior"


def test_unclassified_job_falls_back_to_keyword(monkeypatch):
    """A job the model skipped is filled by the keyword heuristic on its title."""
    _patch_client(monkeypatch, SeniorityResults(items=[_Seniority(i=0, level="mid")]))
    jobs = [{"title": "Developer"}, {"title": "Senior Architect"}]  # job 1 not returned
    classify_seniority(jobs)
    assert jobs[0]["seniority"] == "mid"
    assert jobs[1]["seniority"] == "senior"     # keyword guess from "Senior"


def test_api_failure_uses_keyword_fallback(monkeypatch):
    """If the call raises, every job gets the keyword guess — never fatal."""
    _patch_client(monkeypatch, exc=RuntimeError("boom"))
    jobs = [{"title": "Junior Intern"}, {"title": "Software Engineer"}]
    classify_seniority(jobs)
    assert jobs[0]["seniority"] == "junior" and jobs[1]["seniority"] == "mid"


def test_no_api_key_skips_the_call(monkeypatch):
    """With no API key, classification uses the keyword heuristic without calling the model."""
    monkeypatch.setattr(sen_mod.config, "OPENAI_API_KEY", "")
    _patch_client(monkeypatch, exc=AssertionError("must not call the model"))
    jobs = [{"title": "Lead Developer"}]
    classify_seniority(jobs)
    assert jobs[0]["seniority"] == "senior"


def test_keyword_guess_levels():
    """The pure keyword heuristic: senior / junior markers, else mid."""
    assert _keyword_guess("Senior Engineer") == "senior"
    assert _keyword_guess("Praktikant im Marketing") == "junior"
    assert _keyword_guess("Software Engineer") == "mid"


def test_empty_jobs_short_circuits():
    """No jobs → [] unchanged."""
    assert classify_seniority([]) == []
