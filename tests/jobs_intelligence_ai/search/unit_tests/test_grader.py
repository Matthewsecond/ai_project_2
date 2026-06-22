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
    """Stands in for `client.responses`: `.parse()` returns a canned parsed object
    (mimicking `output_parsed`), or raises `exc` to simulate an API failure."""

    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


class _FakeClient:
    """A fake OpenAI client whose `.responses.parse()` is fully controlled by the test."""

    def __init__(self, parsed=None, exc=None):
        self.responses = _FakeResponses(parsed, exc)


def _jobs(n):
    """n minimal job dicts — only the fields the grader reads for its prompt."""
    return [{"title": f"Job {i}"} for i in range(n)]


def test_applies_parsed_scores_and_bands():
    """Happy path: each job gets the model's score, its "NN%" string, and the correct
    A/B/C band (0.91 → A, 0.50 → C) plus the verbatim match_reason."""
    parsed = _Scores(scores=[_Score(score=0.91, match_reason="strong fit"),
                             _Score(score=0.50, match_reason="partial")])
    out = Grader(_FakeClient(parsed=parsed), GraderConfig()).grade("cv", _jobs(2))
    assert out[0]["score"] == 0.91 and out[0]["grade"] == "A"
    assert out[0]["match_reason"] == "strong fit"
    assert out[1]["score"] == 0.50 and out[1]["grade"] == "C"
    assert out[0]["score_pct"] == "91%"


def test_clamps_out_of_range_scores():
    """Defensive: if the model returns a score outside 0.0–1.0, it's clamped into range
    (1.7 → 1.0, -0.3 → 0.0) so downstream % and banding stay valid."""
    parsed = _Scores(scores=[_Score(score=1.7, match_reason="over"),
                             _Score(score=-0.3, match_reason="under")])
    out = Grader(_FakeClient(parsed=parsed), GraderConfig()).grade("cv", _jobs(2))
    assert out[0]["score"] == 1.0
    assert out[1]["score"] == 0.0


def test_short_reply_fills_missing_with_neutral():
    """If the model returns fewer scores than there are jobs, the unscored jobs default
    to a neutral 0.5 with an empty reason — never an index error or a dropped job."""
    parsed = _Scores(scores=[_Score(score=0.8, match_reason="only one")])  # 1 score, 2 jobs
    out = Grader(_FakeClient(parsed=parsed), GraderConfig()).grade("cv", _jobs(2))
    assert out[0]["score"] == 0.8
    assert out[1]["score"] == 0.5 and out[1]["match_reason"] == ""


def test_model_failure_falls_back_to_neutral():
    """If the API call raises, the whole batch falls back to neutral 0.5 rather than
    crashing the search — grading is best-effort, never fatal."""
    out = Grader(_FakeClient(exc=RuntimeError("boom")), GraderConfig()).grade("cv", _jobs(2))
    assert all(j["score"] == 0.5 for j in out)


def test_empty_jobs_short_circuits():
    """With no jobs to grade, grade() returns [] immediately and makes no model call."""
    assert Grader(_FakeClient(), GraderConfig()).grade("cv", []) == []
