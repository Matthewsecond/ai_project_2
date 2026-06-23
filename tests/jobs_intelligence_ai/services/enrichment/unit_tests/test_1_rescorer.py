"""
Offline unit tests for the Structured-Outputs Rescorer (2.3 #2b).

No network: we patch the module's `get_client` so `responses.parse` returns a canned
`RescoreResults`, then assert the rescorer applies it and degrades gracefully (keeps the
current scores) on failure / empty / short replies.
"""
import jobs_intelligence_ai.services.enrichment.rescorer as rescorer_mod
from jobs_intelligence_ai.services.enrichment.rescorer import Rescorer
from jobs_intelligence_ai.services.enrichment.config import RescoreResults, _ScoredJob


class _FakeResponses:
    """`.parse()` returns a canned RescoreResults (mimicking output_parsed), or raises."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch_client(monkeypatch, parsed=None, exc=None):
    """Point the rescorer module's get_client at a fake whose .responses we control."""
    client = type("C", (), {"responses": _FakeResponses(parsed, exc)})()
    monkeypatch.setattr(rescorer_mod, "get_client", lambda *a, **k: client)


def _jobs():
    return [{"job_id": 1, "score": 0.5, "match_reason": "old1"},
            {"job_id": 2, "score": 0.5, "match_reason": "old2"}]


def test_applies_parsed_scores_and_bands(monkeypatch):
    """Each job takes the model's new score, % string, A/B/C band and reason, in order."""
    _patch_client(monkeypatch, RescoreResults(scores=[
        _ScoredJob(score=0.82, match_reason="strong now"),
        _ScoredJob(score=0.40, match_reason="weaker"),
    ]))
    out = Rescorer().rescore("cv", _jobs())
    assert out[0] == {"job_id": 1, "score": 0.82, "score_pct": "82%",
                      "grade": "A", "match_reason": "strong now"}
    assert out[1]["score"] == 0.40 and out[1]["grade"] == "C"


def test_clamps_out_of_range(monkeypatch):
    """A model score outside 0–1 is clamped into range."""
    _patch_client(monkeypatch, RescoreResults(scores=[
        _ScoredJob(score=1.5, match_reason="over"), _ScoredJob(score=-1.0, match_reason="under")]))
    out = Rescorer().rescore("cv", _jobs())
    assert out[0]["score"] == 1.0 and out[1]["score"] == 0.0


def test_short_reply_keeps_remaining_unchanged(monkeypatch):
    """Fewer scores than jobs → the unscored jobs keep their current score/reason."""
    _patch_client(monkeypatch, RescoreResults(scores=[_ScoredJob(score=0.9, match_reason="one")]))
    out = Rescorer().rescore("cv", _jobs())
    assert out[0]["score"] == 0.9
    assert out[1]["score"] == 0.5 and out[1]["match_reason"] == "old2"


def test_failure_keeps_current_scores(monkeypatch):
    """If the API call raises, every job keeps its current score — never fatal."""
    _patch_client(monkeypatch, exc=RuntimeError("boom"))
    out = Rescorer().rescore("cv", _jobs())
    assert [j["score"] for j in out] == [0.5, 0.5]
    assert [j["match_reason"] for j in out] == ["old1", "old2"]


def test_empty_reply_keeps_current(monkeypatch):
    """An empty scores list also falls back to the current scores."""
    _patch_client(monkeypatch, RescoreResults(scores=[]))
    out = Rescorer().rescore("cv", _jobs())
    assert [j["score"] for j in out] == [0.5, 0.5]


def test_empty_jobs_short_circuits(monkeypatch):
    """No jobs → [] with no model call."""
    _patch_client(monkeypatch, exc=AssertionError("should not be called"))
    assert Rescorer().rescore("cv", []) == []
