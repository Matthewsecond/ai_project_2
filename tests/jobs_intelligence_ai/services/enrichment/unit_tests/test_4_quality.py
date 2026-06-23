"""
Offline unit tests for the Structured-Outputs quality classifier (2.3 #2e).

No network: patch the module's `get_client` so `responses.parse` returns a canned
`QualityResults`. Asserts the AI assessment is applied, skipped jobs get the rule-based
fallback, and an API failure / missing key degrades to the completeness-only heuristic.
"""
import jobs_intelligence_ai.services.enrichment.quality_classifier as qual_mod
from jobs_intelligence_ai.services.enrichment.quality_classifier import classify_quality
from jobs_intelligence_ai.services.enrichment.config import QualityResults, _Quality

_GROUP = {"occ_group": "IT", "count": 10, "mean": 3000.0, "median": 2900.0, "p25": 2500.0, "p75": 3500.0}
_JOBS = lambda: [{"title": "Engineer", "description": "Build APIs.", "salary": "3000"}]


class _FakeResponses:
    """`.parse()` returns a canned QualityResults (mimicking output_parsed), or raises."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch_client(monkeypatch, parsed=None, exc=None):
    client = type("C", (), {"responses": _FakeResponses(parsed, exc)})()
    monkeypatch.setattr(qual_mod, "get_client", lambda *a, **k: client)


def test_applies_model_assessment(monkeypatch):
    """The model's quality fields are written onto the matching job."""
    _patch_client(monkeypatch, QualityResults(items=[
        _Quality(i=0, quality="high", score=0.88, verdict="fair pay", fit="fair", flags=["complete"])]))
    jobs = _JOBS()
    classify_quality(jobs, _GROUP)
    assert jobs[0]["quality"] == "high" and jobs[0]["quality_score"] == 0.88
    assert jobs[0]["quality_fit"] == "fair" and jobs[0]["quality_flags"] == ["complete"]


def test_skipped_job_gets_rule_based_fallback(monkeypatch):
    """A job the model didn't return falls back to the completeness-based estimate."""
    _patch_client(monkeypatch, QualityResults(items=[]))   # model returned nothing
    jobs = _JOBS()
    classify_quality(jobs, _GROUP)
    assert jobs[0]["quality"] in ("high", "mid", "low")
    assert jobs[0]["quality_fit"] == "unknown"             # fallback marker


def test_api_failure_uses_fallback(monkeypatch):
    """If the call raises, every job gets the rule-based fallback — never fatal."""
    _patch_client(monkeypatch, exc=RuntimeError("boom"))
    jobs = _JOBS()
    classify_quality(jobs, _GROUP)
    assert "quality" in jobs[0] and jobs[0]["quality_fit"] == "unknown"


def test_no_api_key_uses_fallback(monkeypatch):
    """With no API key, quality is estimated without calling the model."""
    monkeypatch.setattr(qual_mod.config, "OPENAI_API_KEY", "")
    _patch_client(monkeypatch, exc=AssertionError("must not call the model"))
    jobs = _JOBS()
    classify_quality(jobs, _GROUP)
    assert jobs[0]["quality"] in ("high", "mid", "low")


def test_empty_jobs_short_circuits():
    """No jobs → [] unchanged."""
    assert classify_quality([], _GROUP) == []
