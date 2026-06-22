"""
Offline unit tests for the Structured-Outputs grader (Stage 2.1b).

No network: we mock the single LLM boundary — `client.responses.parse` — and return
a Pydantic `_Scores`, then assert the grader applies it correctly and falls back to
neutral scores when the model fails or returns too few entries. This is the pattern
every service conversion will use to get offline coverage.
"""
import pytest

from jobs_intelligence_ai.search.grader import Grader, _Score, _Scores
from jobs_intelligence_ai.search.config import GraderConfig


class _FakeResponses:
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


class _FakeClient:
    def __init__(self, parsed=None, exc=None):
        self.responses = _FakeResponses(parsed, exc)


def _jobs(n):
    return [{"title": f"Job {i}"} for i in range(n)]


def test_applies_parsed_scores_and_bands():
    parsed = _Scores(scores=[_Score(score=0.91, match_reason="strong fit"),
                             _Score(score=0.50, match_reason="partial")])
    out = Grader(_FakeClient(parsed=parsed), GraderConfig()).grade("cv", _jobs(2))
    assert out[0]["score"] == 0.91 and out[0]["grade"] == "A"
    assert out[0]["match_reason"] == "strong fit"
    assert out[1]["score"] == 0.50 and out[1]["grade"] == "C"
    assert out[0]["score_pct"] == "91%"


def test_clamps_out_of_range_scores():
    parsed = _Scores(scores=[_Score(score=1.7, match_reason="over"),
                             _Score(score=-0.3, match_reason="under")])
    out = Grader(_FakeClient(parsed=parsed), GraderConfig()).grade("cv", _jobs(2))
    assert out[0]["score"] == 1.0
    assert out[1]["score"] == 0.0


def test_short_reply_fills_missing_with_neutral():
    parsed = _Scores(scores=[_Score(score=0.8, match_reason="only one")])  # 1 score, 2 jobs
    out = Grader(_FakeClient(parsed=parsed), GraderConfig()).grade("cv", _jobs(2))
    assert out[0]["score"] == 0.8
    assert out[1]["score"] == 0.5 and out[1]["match_reason"] == ""


def test_model_failure_falls_back_to_neutral():
    out = Grader(_FakeClient(exc=RuntimeError("boom")), GraderConfig()).grade("cv", _jobs(2))
    assert all(j["score"] == 0.5 for j in out)


def test_empty_jobs_short_circuits():
    assert Grader(_FakeClient(), GraderConfig()).grade("cv", []) == []
